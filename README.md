# НИР — блог научных публикаций

Система генерации, проверки и публикации научных статей в формате Markdown.

## Архитектура

1. Telegram-бот получает запрос на генерацию статьи.
2. OpenRouter генерирует Markdown.
3. Бот сохраняет файл и передаёт его на сервер через SFTP.
4. systemd-импортёр переносит файл из `incoming/` в `drafts/`.
5. Редактор проверяет и исправляет черновик через SSH.
6. Publisher перемещает статью в `articles/` и записывает метаданные в PostgreSQL.
7. FastAPI отображает опубликованную статью на сайте.

## Компоненты

- `bot/` — Telegram-бот, OpenRouter, SFTP-клиент.
- `blog/` — FastAPI, HTML-шаблоны, CSS, Markdown.
- `database/` — начальная SQL-схема PostgreSQL.
- `deploy/` — Linux-импортёр и systemd-конфигурация.
- `compose.yaml` — Docker Compose.

## Запуск сайта

Необходимы Docker и Docker Compose.

```bash
cp .env.example .env
```

Установите собственный пароль PostgreSQL в `.env`.

```bash
docker compose up -d --build
docker compose ps
```

Локальный адрес сайта:

http://localhost:8000/

API:

- `/health`
- `/api/articles`
- `/api/articles/{id}`

Сайт поддерживает фильтрацию публикаций по авторам.

## Запуск Telegram-бота

Необходим Python и доступ к Telegram API и OpenRouter.

```bash
cd bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env` настоящими значениями Telegram, OpenRouter и SFTP.

Запуск:

```bash
python main.py
```

На Windows активация виртуального окружения отличается:

```powershell
.\.venv\Scripts\Activate.ps1
```

Важно: одновременно должен работать только один polling-экземпляр бота с одним Telegram-токеном.

## Серверный импорт черновиков

Импортёр предназначен для Linux с systemd.

Его исходники находятся в `deploy/`:

- `nir-import-drafts.py`
- `importer.conf.example`
- `systemd/nir-import-drafts.service`
- `systemd/nir-import-drafts.timer`

Перед установкой необходимо отдельно настроить SSH/SFTP-сервер, ограниченного пользователя загрузки и права доступа к каталогам.

Установка на Linux-сервере из корня проекта:

```bash
sudo install -D -m 755 deploy/nir-import-drafts.py /usr/local/sbin/nir-import-drafts.py
sudo install -d -m 755 /etc/nir-blog
sudo install -m 600 deploy/importer.conf.example /etc/nir-blog/importer.conf
sudo install -m 644 deploy/systemd/nir-import-drafts.service /etc/systemd/system/
sudo install -m 644 deploy/systemd/nir-import-drafts.timer /etc/systemd/system/
```

Перед запуском измените `/etc/nir-blog/importer.conf`, указав реальные пути и пользователя редактора.

Затем:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nir-import-drafts.timer
```

Проверка:

```bash
systemctl status nir-import-drafts.timer
sudo journalctl -u nir-import-drafts.service -n 30 --no-pager
```

Импортёр запускается с системными привилегиями, поэтому доступ к его скрипту и конфигурации должен быть ограничен администратором.

## Работа редактора

1. Подключиться к серверу по SSH или через VS Code Remote SSH.
2. Открыть `blog/content/drafts/`.
3. Проверить и отредактировать Markdown-файл.
4. Сохранить изменения.
5. Выполнить команду публикации из корня проекта.

Просмотр авторов:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT id, full_name FROM authors ORDER BY id;"'
```

Публикация:

```bash
docker compose run --rm publisher filename.md AUTHOR_ID
```

Имя файла и ID автора необходимо заменить на реальные значения.

После публикации статья перемещается в `articles/` и становится доступной на сайте.

## Безопасность и особенности

- Настоящие `.env` не включаются в Git.
- Приватные SSH-ключи не включаются в Git.
- Черновики не отображаются публичным сайтом.
- Каталог опубликованных статей подключается к web-контейнеру только для чтения.
- Telegram-бот использует ограниченный SFTP-доступ.
- Редактор и бот используют разные учётные записи.
- PostgreSQL хранит данные в Docker volume.
- Для публичного развёртывания необходимо отдельно настроить HTTPS, доступ к сайту и резервное копирование.
- Автоматическая установка и настройка ограниченного SFTP-пользователя пока не реализованы.