
import os
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt


SECTIONS = [
    {"id": 1, "name": "BehaviorTree.CPP", "description": "Деревья поведения: структура, выполнение и организация управления."},
    {"id": 2, "name": "SMACH", "description": "Конечные автоматы, состояния и иерархия поведения."},
    {"id": 3, "name": "Коммуникации", "description": "Обмен данными и взаимодействие роботов."},
    {"id": 4, "name": "Синхронизация", "description": "Согласование действий и выполнение совместных задач."},
    {"id": 5, "name": "Интеграция и анализ", "description": "Сопоставление подходов, критерии оценки и общие выводы."},
]

app = FastAPI(title="НИР — лабораторный журнал")

app.mount(
    "/static",
    StaticFiles(directory="/app/static"),
    name="static",
)

templates = Jinja2Templates(directory="/app/templates")

markdown = MarkdownIt("commonmark", {"html": False})

ARTICLES_DIR = Path(
    os.environ.get("ARTICLES_DIR", "/app/content/articles")
).resolve()


def db_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "db"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=dict_row,
    )


def clean_inline(text: str) -> str:
    """Убирает простую Markdown-разметку из короткого текста."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_~]", "", text)
    return " ".join(text.split())


def extract_metadata(markdown_text: str):
    """Получает заголовок H1 и первый обычный абзац."""
    match = re.search(
        r"^#\s+(.+?)\s*$",
        markdown_text,
        flags=re.MULTILINE,
    )

    title = clean_inline(match.group(1)) if match else None
    description = None

    if match:
        paragraph = []

        for raw_line in markdown_text[match.end():].splitlines():
            line = raw_line.strip()

            if not line:
                if paragraph:
                    break
                continue

            if line.startswith(
                ("#", "```", "-", "* ", "![", "|", ">")
            ):
                if paragraph:
                    break
                continue

            paragraph.append(line)

        if paragraph:
            description = clean_inline(" ".join(paragraph))
            description = description[:300]

    return title, description


def resolve_article_path(filename: str) -> Path:
    if (
        not filename.endswith(".md")
        or Path(filename).name != filename
        or filename.startswith(".")
    ):
        raise HTTPException(
            status_code=500,
            detail="Недопустимое имя файла в базе",
        )

    file_path = ARTICLES_DIR / filename

    if not file_path.is_file() or file_path.is_symlink():
        raise HTTPException(
            status_code=404,
            detail="Файл статьи отсутствует",
        )

    return file_path


def prepare_metadata(article: dict, markdown_text: str | None = None):
    """Дополняет метаданные для отображения на сайте."""
    if not article.get("title") or not article.get("description"):
        if markdown_text is None:
            file_path = resolve_article_path(article["filename"])
            markdown_text = file_path.read_text(encoding="utf-8")

        extracted_title, extracted_description = extract_metadata(
            markdown_text
        )

        if not article.get("title"):
            article["title"] = extracted_title

        if not article.get("description"):
            article["description"] = extracted_description

    article["title"] = (
        clean_inline(article["title"])
        if article.get("title")
        else f"Публикация №{article['id']}"
    )

    article["description"] = (
        clean_inline(article["description"])[:300]
        if article.get("description")
        else "Научно-исследовательская публикация лаборатории."
    )

    return article

def get_authors():
    with db_connection() as conn:
        return conn.execute(
            """
            SELECT id, full_name
            FROM authors
            ORDER BY full_name
            """
        ).fetchall()

def get_articles(author_id: int | None = None, section_id: int | None = None):
    with db_connection() as conn:
        articles = conn.execute(
            """
            SELECT
                a.id,
                a.filename,
                a.section_id,
                s.name AS section_name,
                a.title,
                a.description,
                a.published_at,
                au.full_name AS author
            FROM articles a
            JOIN authors au ON a.author_id = au.id
            LEFT JOIN sections s ON a.section_id = s.id
            WHERE (%s::BIGINT IS NULL OR a.author_id = %s)
            AND (%s::BIGINT IS NULL OR a.section_id = %s)
            ORDER BY a.published_at DESC
            """,
            (author_id, author_id, section_id, section_id),
        ).fetchall()

    return [
        prepare_metadata(article)
        for article in articles
    ]

def get_article(article_id: int):
    with db_connection() as conn:
        article = conn.execute(
            """
            SELECT
                a.id,
                a.filename,
                a.section_id,
                s.name AS section_name,
                a.title,
                a.description,
                a.published_at,
                au.full_name AS author
            FROM articles a
            JOIN authors au ON a.author_id = au.id
            LEFT JOIN sections s ON a.section_id = s.id
            WHERE a.id = %s
            """,
            (article_id,),
        ).fetchone()

    if article is None:
        raise HTTPException(
            status_code=404,
            detail="Статья не найдена",
        )

    file_path = resolve_article_path(article["filename"])
    markdown_text = file_path.read_text(encoding="utf-8")

    article = prepare_metadata(article, markdown_text)
    article["markdown"] = markdown_text

    return article


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/articles")
def api_articles(author_id: int | None = None, section_id: int | None = None):
    return get_articles(author_id, section_id)


@app.get("/api/articles/{article_id}")
def api_article(article_id: int):
    return get_article(article_id)

@app.get("/", response_class=HTMLResponse)
def home(request: Request, section_id: int | None = None, author_id: int | None = None):
    if section_id or author_id:
        target = f"/directions/{section_id}" if section_id else "/publications"
        if author_id:
            target += f"?author_id={author_id}"
        return RedirectResponse(target, status_code=307)
    return templates.TemplateResponse(request, "home.html", {"sections": SECTIONS, "page": "home", "selected_section_id": None})

@app.get("/publications", response_class=HTMLResponse)
@app.get("/directions/{section_id}", response_class=HTMLResponse)
def publications(request: Request, section_id: int | None = None, author_id: str | None = None):
    section = next((s for s in SECTIONS if s["id"] == section_id), None)
    if section_id is not None and section is None:
        raise HTTPException(status_code=404, detail="Направление не найдено")
    if author_id and (not author_id.isdecimal() or len(author_id) > 18):
        raise HTTPException(status_code=400, detail="Некорректный ID автора")
    selected_author_id = int(author_id) if author_id else None
    articles = get_articles(selected_author_id, section_id)
    return templates.TemplateResponse(request, "publications.html", {
        "sections": SECTIONS, "section": section, "selected_section_id": section_id,
        "authors": get_authors(), "selected_author_id": selected_author_id,
        "articles": articles, "page": "publications",
    })

@app.get("/articles/{article_id}", response_class=HTMLResponse)
def article_page(request: Request, article_id: int):
    article = get_article(article_id)

    # Заголовок H1 будет в шапке страницы.
    # Убираем его из тела, чтобы не дублировать.
    body_markdown = re.sub(
        r"^#\s+.+(?:\n|$)",
        "",
        article["markdown"],
        count=1,
        flags=re.MULTILINE,
    ).lstrip()

    # HTML внутри Markdown отключён настройкой markdown-it.
    article["html"] = markdown.render(body_markdown)

    return templates.TemplateResponse(
        request,
        "article.html",
        {"article": article, "sections": SECTIONS, "selected_section_id": article.get("section_id"), "page": "article"},
    )
