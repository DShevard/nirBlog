
#!/usr/bin/env bash

set -euo pipefail

# Переходим в корень проекта
cd "$(dirname "$0")/.."

# Создаём папку для резервной копии
timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
backup_dir="backups/$timestamp"

mkdir -p "$backup_dir"

echo "Начинаем резервное копирование..."

if [[ "${1:-}" == "--local" ]]; then

    # Локальный тест без SSH
    echo "Режим: локальный"

    tar -czf "$backup_dir/content.tar.gz" \
        -C blog/content articles drafts

    docker compose exec -T db sh -c \
        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
        > "$backup_dir/database.dump"

else

    # Получаем настройки подключения
    : "${SSH_TARGET:?Не указан SSH_TARGET}"
    : "${REMOTE_PROJECT_DIR:?Не указан REMOTE_PROJECT_DIR}"

    # Проверяем формат удалённого пути
    if [[ ! "$REMOTE_PROJECT_DIR" =~ ^/[a-zA-Z0-9_./-]+$ ]]; then
        echo "Укажи абсолютный путь к проекту без пробелов."
        exit 1
    fi

    echo "Режим: удалённый сервер"

    # Скачиваем статьи и черновики
    echo "Скачиваем Markdown-файлы..."

    ssh "$SSH_TARGET" \
        "cd '$REMOTE_PROJECT_DIR' && tar -czf - -C blog/content articles drafts" \
        > "$backup_dir/content.tar.gz"

    # Скачиваем базу PostgreSQL
    echo "Скачиваем PostgreSQL..."

    ssh "$SSH_TARGET" \
        "cd '$REMOTE_PROJECT_DIR' && docker compose exec -T db sh -c 'pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Fc'" \
        > "$backup_dir/database.dump"

fi

# Проверяем архив и наличие дампа
tar -tzf "$backup_dir/content.tar.gz" > /dev/null
test -s "$backup_dir/database.dump"

echo "Резервное копирование завершено!"
echo "Файлы сохранены в: $backup_dir"
