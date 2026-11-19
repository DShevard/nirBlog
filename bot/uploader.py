
import os
import shutil
import sys
import uuid
from pathlib import Path

import paramiko
from dotenv import load_dotenv


load_dotenv()


def upload_article(filepath: str) -> None:
    local_file = Path(filepath).resolve()

    if not local_file.is_file():
        raise FileNotFoundError("Файл не найден")

    if local_file.suffix.lower() != ".md":
        raise ValueError("Разрешены только Markdown-файлы")

    host = os.environ["SFTP_HOST"]
    port = int(os.getenv("SFTP_PORT", "22"))
    username = os.environ["SFTP_USER"]
    private_key = os.environ["SFTP_PRIVATE_KEY"]
    remote_dir = os.environ["SFTP_REMOTE_DIR"]

    remote_file = f"{remote_dir}/{local_file.name}"

    # Временный файл с уникальным именем
    temporary_file = (
        f"{remote_file}.{uuid.uuid4().hex}.uploading"
    )

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            key_filename=private_key,
            look_for_keys=False,
            allow_agent=False,
            timeout=15,
        )

        with ssh.open_sftp() as sftp:
            with local_file.open("rb") as source:
                # Загружаем файл под временным именем
                with sftp.open(temporary_file, "wbx") as target:
                    shutil.copyfileobj(source, target)

            # После завершения загрузки переименовываем
            sftp.rename(temporary_file, remote_file)

        print(f"Файл отправлен: {remote_file}")

    finally:
        ssh.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование: python uploader.py file.md")
        sys.exit(1)

    try:
        upload_article(sys.argv[1])
    except Exception as error:
        print(f"Ошибка SFTP: {error}")
        sys.exit(1)
