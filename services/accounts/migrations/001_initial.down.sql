-- Rollback for 001_initial.sql
DROP INDEX IF EXISTS idx_friendships_friend;
DROP INDEX IF EXISTS idx_friendships_user;
DROP TABLE IF EXISTS friendships;
DROP INDEX IF EXISTS idx_location_shares_location;
DROP INDEX IF EXISTS idx_location_shares_active;
DROP INDEX IF EXISTS idx_location_shares_user;
DROP TABLE IF EXISTS location_shares;
DROP INDEX IF EXISTS idx_favorites_user;
DROP TABLE IF EXISTS favorites;
DROP INDEX IF EXISTS idx_memories_visibility;
DROP INDEX IF EXISTS idx_memories_location;
DROP INDEX IF EXISTS idx_memories_user;
DROP TABLE IF EXISTS memories;
DROP TYPE IF EXISTS media_type;
DROP TYPE IF EXISTS favorite_kind;
DROP TYPE IF EXISTS visibility;
DROP TABLE IF EXISTS users;
