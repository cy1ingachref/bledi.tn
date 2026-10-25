-- Rollback for 002_add_media_key.sql
ALTER TABLE memories DROP COLUMN IF EXISTS media_key;
DROP INDEX IF EXISTS idx_memories_media_key;
