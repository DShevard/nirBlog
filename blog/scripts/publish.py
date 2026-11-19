import os
import re
import sys
from pathlib import Path

import psycopg


DRAFTS_DIR = Path("/app/content/drafts")
ARTICLES_DIR = Path("/app/content/articles")


def extract_metadata(markdown: str) -> tuple[str, str | None]:
    # Ищем первый заголовок уровня H1.
    match = re.search(
        r"^#\s+(.+?)\s*$",
        markdown,
        flags=re.MULTILINE,
    )

    if match is None:
        raise ValueError(
            "В статье отсутствует заголовок первого уровня (#)"
        )

    title = match.group(1).strip().rstrip("#").strip()

    if not title:
        raise ValueError("Заголовок статьи пустой")

    # Первый обычный абзац после заголовка
    # используем как описание статьи.
    paragraph = []

    for line in markdown[match.end():].splitlines():
        line = line.strip()

        if not line:
            if paragraph:
                break
            continue

        if line.startswith(("#", "```", "-", "* ", "![", "|", ">")):
            if paragraph:
                break
            continue

        paragraph.append(line)

    description = " ".join(paragraph).strip()

    if description:
        description = description[:300]
    else:
        description = None

    return title, description


def publish(filename: str, author_id: int, section_id: int) -> None:
    if section_id not in range(1, 6):
        raise ValueError("ID направления должен быть от 1 до 5")
    if (
        Path(filename).name != filename
        or not filename.endswith(".md")
        or filename.startswith(".")
    ):
        raise ValueError("Недопустимое имя Markdown-файла")

    source = DRAFTS_DIR / filename
    target = ARTICLES_DIR / filename

    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError("Черновик не найден")

    if target.exists():
        raise FileExistsError(
            "Статья с таким именем уже опубликована"
        )

    # Читаем данные до перемещения и записи в БД.
    markdown = source.read_text(encoding="utf-8")
    title, description = extract_metadata(markdown)

    moved = False

    try:
        with psycopg.connect(
            host=os.environ["DB_HOST"],
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        ) as conn:

            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM authors WHERE id = %s",
                    (author_id,),
                )

                if cursor.fetchone() is None:
                    raise ValueError(
                        "Автор с таким ID не найден"
                    )

                cursor.execute(
                    "SELECT id FROM articles WHERE filename = %s",
                    (filename,),
                )

                if cursor.fetchone() is not None:
                    raise ValueError(
                        "Статья уже зарегистрирована в БД"
                    )

                # Перемещаем проверенный Markdown.
                source.rename(target)
                moved = True

                # Регистрируем публикацию в PostgreSQL.
                cursor.execute(
                    """
                    INSERT INTO articles (
                        filename,
                        title,
                        description,
                        author_id,
                        section_id
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        filename,
                        title,
                        description,
                        author_id,
                        section_id,
                    ),
                )

                article_id = cursor.fetchone()[0]

        print(f"Статья опубликована! ID: {article_id}")
        print(f"Заголовок: {title}")

    except Exception:
        if moved and target.exists() and not source.exists():
            target.rename(source)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Использование: publish.py filename.md author_id section_id")
        sys.exit(1)

    try:
        publish(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    except (
        ValueError,
        OSError,
        UnicodeError,
        psycopg.Error,
    ) as error:
        print(f"Ошибка публикации: {error}")
        sys.exit(1)
