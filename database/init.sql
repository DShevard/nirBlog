-- Initial database schema for the NIR blog.
-- Runs only when the PostgreSQL data volume is initialized.

-- Authors
CREATE TABLE IF NOT EXISTS authors (
    id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL
);

-- Published articles
CREATE TABLE IF NOT EXISTS articles (
    id BIGSERIAL PRIMARY KEY,

    filename TEXT NOT NULL UNIQUE,
    title TEXT,
    description TEXT,

    author_id BIGINT NOT NULL
        REFERENCES authors(id),

    published_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW()
);
BEGIN;
CREATE TABLE IF NOT EXISTS sections (id BIGINT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
INSERT INTO sections (id,name) VALUES
(1,'BehaviorTree.CPP'), (2,'SMACH'), (3,'Коммуникации'), (4,'Синхронизация'), (5,'Интеграция и анализ')
ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS section_id BIGINT REFERENCES sections(id);
CREATE INDEX IF NOT EXISTS articles_section_id_idx ON articles(section_id);
COMMIT;
