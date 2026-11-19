BEGIN;
CREATE TABLE IF NOT EXISTS sections (id BIGINT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
INSERT INTO sections (id,name) VALUES
(1,'BehaviorTree.CPP'), (2,'SMACH'), (3,'Коммуникации'), (4,'Синхронизация'), (5,'Интеграция и анализ')
ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS section_id BIGINT REFERENCES sections(id);
CREATE INDEX IF NOT EXISTS articles_section_id_idx ON articles(section_id);
COMMIT;
