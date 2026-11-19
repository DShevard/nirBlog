"""Download publicly accessible HTML and PDF sources for article drafting.

Sources are untrusted: never execute embedded content or treat it as instructions.
"""

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

MAX_SOURCES = 6
MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 12000
MAX_REDIRECTS = 4
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class Source:
    number: int
    url: str
    title: str
    text: str


class SourceError(ValueError):
    """The supplied sources could not be safely read."""


def extract_urls(request: str) -> list[str]:
    """Extract URLs while preserving the author's order and removing duplicates."""
    unique = []
    for match in URL_PATTERN.finditer(request):
        url = match.group(0).rstrip(".,;)]}")
        if url not in unique:
            unique.append(url)
    if not unique:
        raise SourceError("Укажи хотя бы одну ссылку на первоисточник в запросе /article.")
    if len(unique) > MAX_SOURCES:
        raise SourceError(f"Укажи не более {MAX_SOURCES} источников за один запрос.")
    return unique


async def _check_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise SourceError("Разрешены только обычные HTTP/HTTPS-ссылки.")
    if parsed.username or parsed.password:
        raise SourceError("Ссылки со встроенными логинами и паролями запрещены.")
    host = parsed.hostname
    if host.lower() == "localhost" or host.endswith(".localhost"):
        raise SourceError("Локальные адреса запрещены.")
    try:
        port = parsed.port
    except ValueError as error:
        raise SourceError("Некорректный порт в URL.") from error
    if port not in (None, 80, 443):
        raise SourceError("Необычные порты в ссылках не разрешены.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except (OSError, UnicodeError) as error:
        raise SourceError(f"Не удалось определить адрес сайта: {host}") from error
    if not infos:
        raise SourceError(f"Не удалось определить адрес сайта: {host}")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise SourceError("Локальные и служебные сетевые адреса запрещены.")


def _extract_html(content: bytes, encoding: str | None, url: str) -> tuple[str, str]:
    soup = BeautifulSoup(content, "html.parser", from_encoding=encoding)
    title = soup.title.get_text(" ", strip=True) if soup.title else url
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    lines = (line.strip() for line in main.get_text("\n").splitlines())
    text = "\n".join(line for line in lines if line)
    if len(text) < 200:
        raise SourceError("На странице не удалось извлечь достаточно текста (возможно, нужен JavaScript или доступ по подписке).")
    return title[:240], text[:MAX_TEXT_CHARS]


def _extract_pdf(content: bytes, url: str) -> tuple[str, str]:
    try:
        pdf = PdfReader(BytesIO(content), strict=False)
        title = str(pdf.metadata.title or url) if pdf.metadata else url
        text = "\n".join(page.extract_text() or "" for page in pdf.pages[:15])
    except Exception as error:
        raise SourceError("PDF нельзя прочитать как текст.") from error
    if len(text.strip()) < 200:
        raise SourceError("В PDF недостаточно доступного текста (возможно, это скан).")
    return title[:240], text[:MAX_TEXT_CHARS]


async def _download(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await _check_public_url(current)
        try:
            async with client.stream("GET", current, follow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise SourceError("Переадресация без адреса назначения.")
                    current = str(response.url.join(location))
                    continue
                response.raise_for_status()
                ctype = response.headers.get("content-type", "").lower()
                if not any(kind in ctype for kind in ("text/html", "application/pdf", "text/plain", "application/octet-stream")):
                    raise SourceError(f"Неподдерживаемый тип документа: {ctype or 'не указан'}")
                buf = bytearray()
                async for chunk in response.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_BYTES:
                        raise SourceError("Документ слишком большой для автоматической обработки.")
                if "application/pdf" in ctype or bytes(buf).startswith(b"%PDF-"):
                    return _extract_pdf(bytes(buf), current)
                if "text/plain" in ctype:
                    plain = bytes(buf).decode(response.encoding or "utf-8", errors="replace").strip()
                    if len(plain) < 200:
                        raise SourceError("В документе недостаточно текста.")
                    return current, plain[:MAX_TEXT_CHARS]
                if "application/octet-stream" in ctype:
                    raise SourceError("Неизвестный двоичный формат документа.")
                return _extract_html(bytes(buf), response.encoding, current)
        except httpx.HTTPError as error:
            raise SourceError(f"Сайт не ответил корректно: {type(error).__name__}") from error
    raise SourceError("Слишком много переадресаций.")


async def load_sources(request: str) -> list[Source]:
    """Read all supplied URLs, or fail rather than cite unreadable documents."""
    urls = extract_urls(request)
    result: list[Source] = []
    failures: list[str] = []
    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, headers={"User-Agent": "NIR-Research-Bot/1.0"}) as client:
        for number, url in enumerate(urls, start=1):
            try:
                title, content = await _download(client, url)
                result.append(Source(number, url, title, content))
            except SourceError as error:
                failures.append(f"{number}. {url} — {error}")
    if failures:
        raise SourceError("Не получилось прочитать все источники:\n" + "\n".join(failures) + "\nУбери недоступные ссылки или замени их доступными.")
    return result
