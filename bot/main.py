
import asyncio
import os
import re
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from generator import generate_article
from uploader import upload_article


load_dotenv()

GENERATED_DIR = Path(__file__).resolve().parent / "generated"
GENERATED_DIR.mkdir(exist_ok=True)


TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g",
    "д": "d", "е": "e", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
}


def extract_title(markdown: str) -> str:
    match = re.search(
        r"^#\s+(.+?)\s*$",
        markdown,
        flags=re.MULTILINE,
    )

    if match is None:
        raise ValueError(
            "В статье отсутствует заголовок первого уровня (#)"
        )

    return match.group(1).strip().rstrip("#").strip()


def make_filename(title: str) -> str:
    latin = "".join(
        TRANSLIT.get(char, char)
        for char in title.lower()
    )

    slug = re.sub(r"[^a-z0-9]+", "-", latin)
    slug = slug.strip("-")[:70].rstrip("-")

    if not slug:
        slug = "article"

    unique_id = uuid4().hex[:8]

    return f"{slug}-{unique_id}.md"



async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Привет! Я бот для подготовки научных статей НИР.\n\n"
        "Для генерации отправь команду /article и укажи:\n"
        "1. Тему статьи.\n"
        "2. Ссылки на первоисточники.\n"
        "3. Особые пожелания (необязательно).\n\n"
        "Общие требования к структуре, стилю и ссылкам "
        "применяются автоматически."
    )



async def article(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    materials = update.message.text.partition(" ")[2].strip()

    if not materials:
        await update.message.reply_text(
            "Укажи тему и материалы после команды /article."
        )
        return

    await update.message.reply_text("Генерирую статью...")

    try:
        article_text = await generate_article(materials)

        title = extract_title(article_text)
        filename = make_filename(title)
        filepath = GENERATED_DIR / filename

        filepath.write_text(
            article_text,
            encoding="utf-8",
        )

        with filepath.open("rb") as file:
            await update.message.reply_document(
                document=file,
                filename=filename,
                caption=f"Черновик: {title[:180]}",
            )

        try:
            await asyncio.to_thread(
                upload_article,
                str(filepath),
            )

            await update.message.reply_text(
                "Статья загружена в incoming/.\n"
                "Автоматический импорт перенесёт её в drafts/ "
                "для проверки редактором."
            )

        except Exception as error:
            print(f"SFTP error: {error}")

            await update.message.reply_text(
                "Статья создана, но не удалось загрузить "
                "её на сервер. Локальная копия сохранена."
            )

    except (
        httpx.HTTPError,
        ValueError,
        KeyError,
        IndexError,
    ) as error:
        print(f"Generation error: {error}")

        await update.message.reply_text(
            "Ошибка генерации или обработки статьи. "
            "Подробности в терминале."
        )


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("article", article))

    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
