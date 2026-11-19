#!/usr/bin/env python3

import os
import pwd
import re
import stat
import uuid
from pathlib import Path

INCOMING = Path(os.environ["NIR_INCOMING_DIR"])
DRAFTS = Path(os.environ["NIR_DRAFTS_DIR"])

EDITOR = pwd.getpwnam(os.environ["NIR_EDITOR_USER"])
MAX_SIZE = 1024 * 1024  # 1 MiB

def import_drafts():
    for source in sorted(INCOMING.iterdir()):
        # Принимаем только простые имена Markdown-файлов.
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.md", source.name):
            continue

        temp = None

        try:
            # Не следуем по символическим ссылкам.
            fd = os.open(
                source,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            )

            with os.fdopen(fd, "rb") as file:
                info = os.fstat(file.fileno())

                if not stat.S_ISREG(info.st_mode):
                    continue

                if info.st_size == 0 or info.st_size > MAX_SIZE:
                    print(f"Пропущен (размер): {source.name}")
                    continue

                data = file.read(MAX_SIZE + 1)

                # Проверяем, что файл не изменился во время чтения.
                after = os.fstat(file.fileno())

                if (
                    len(data) != info.st_size
                    or info.st_size != after.st_size
                    or info.st_mtime_ns != after.st_mtime_ns
                ):
                    print(f"Пропущен (файл изменяется): {source.name}")
                    continue

            data.decode("utf-8")

            destination = DRAFTS / source.name
            temp = DRAFTS / f".import-{uuid.uuid4().hex}.tmp"

            # Сначала создаём временный файл в папке редактора.
            with open(temp, "xb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())

                os.fchown(file.fileno(), EDITOR.pw_uid, EDITOR.pw_gid)
                os.fchmod(file.fileno(), 0o644)

            # Атомарно добавляем готовый файл без перезаписи.
            try:
                os.link(temp, destination)
            except FileExistsError:
                print(f"Уже существует в drafts: {source.name}")
                continue

            # Удаляем исходник только после успешного импорта.
            source.unlink()

            print(f"Импортировано: {source.name}")

        except (OSError, UnicodeError) as error:
            print(f"Ошибка {source.name}: {error}")

        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)


if __name__ == "__main__":
    import_drafts()
