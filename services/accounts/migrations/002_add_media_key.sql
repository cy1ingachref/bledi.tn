-- Memories can carry a photo uploaded through POST /api/v1/memories.
--
-- media_key is the object key of that photo inside the media root; media_url is
-- the absolute URL derived from it. The key is the source of truth: a bucket or
-- host change rewrites the URL without touching the key.
--
-- 001_initial.sql is deliberately not edited: sqlx checksums the migrations it
-- has already run, and rewriting one of them breaks every existing database.

ALTER TABLE memories ADD COLUMN IF NOT EXISTS media_key TEXT;

-- One photo per key, so two memories can never claim the same file.
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_media_key
    ON memories(media_key) WHERE media_key IS NOT NULL;
