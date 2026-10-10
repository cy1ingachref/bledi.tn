-- bledi.tn database schema
-- Run with: sqlx migrate run

-- ── Enum types ──────────────────────────────────────────────────────────────

CREATE TYPE transport_mode AS ENUM ('bus', 'metro', 'tram', 'train', 'rfr', 'taxi', 'louaj', 'walk');
CREATE TYPE visibility AS ENUM ('public', 'friends', 'private');
CREATE TYPE media_type AS ENUM ('image', 'video');
CREATE TYPE favorite_kind AS ENUM ('station', 'line', 'place');

-- ── Users ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Stations ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stations (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    lat   DOUBLE PRECISION NOT NULL,
    lon   DOUBLE PRECISION NOT NULL,
    modes TEXT[] NOT NULL DEFAULT '{}',
    city  TEXT
);

CREATE INDEX IF NOT EXISTS idx_stations_location ON stations USING gist (
    ll_to_earth(lat, lon)
);

-- ── Lines ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS lines (
    id          TEXT PRIMARY KEY,
    number      TEXT NOT NULL,
    name        TEXT NOT NULL,
    mode        transport_mode NOT NULL,
    operator    TEXT,
    color       TEXT,
    station_ids TEXT[] NOT NULL DEFAULT '{}'
);

-- ── Memories ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS memories (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lat              DOUBLE PRECISION NOT NULL,
    lon              DOUBLE PRECISION NOT NULL,
    title            TEXT,
    description      TEXT,
    media_url        TEXT NOT NULL,
    media_type       media_type NOT NULL,
    visibility       visibility NOT NULL DEFAULT 'public',
    unlock_radius_m  DOUBLE PRECISION NOT NULL DEFAULT 200.0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_location ON memories USING gist (
    ll_to_earth(lat, lon)
);
CREATE INDEX IF NOT EXISTS idx_memories_visibility ON memories(visibility);

-- ── Favorites ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS favorites (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       favorite_kind NOT NULL,
    ref_id     TEXT NOT NULL,
    label      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, kind, ref_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);

-- ── Location shares ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS location_shares (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    accuracy_m  DOUBLE PRECISION,
    note        TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    expires_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_location_shares_user ON location_shares(user_id);
CREATE INDEX IF NOT EXISTS idx_location_shares_active ON location_shares(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_location_shares_location ON location_shares USING gist (
    ll_to_earth(lat, lon)
);

-- ── Friendships (for friends-only visibility) ───────────────────────────────

CREATE TABLE IF NOT EXISTS friendships (
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status     TEXT NOT NULL DEFAULT 'pending', -- pending, accepted, blocked
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, friend_id)
);

CREATE INDEX IF NOT EXISTS idx_friendships_user ON friendships(user_id);
CREATE INDEX IF NOT EXISTS idx_friendships_friend ON friendships(friend_id);
