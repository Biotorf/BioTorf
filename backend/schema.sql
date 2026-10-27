-- BIOTORF Business OS · схема PostgreSQL (идемпотентна, применяется при старте)
-- Соответствует прежним таблицам SQLite: comms, chat_drafts, channels,
-- channel_accounts, crm_records, logistics_docs, users.

CREATE TABLE IF NOT EXISTS comms (
    seq          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- позиция long-poll-ленты (аналог rowid)
    id           TEXT NOT NULL UNIQUE,
    kind         TEXT NOT NULL,
    dir          TEXT NOT NULL DEFAULT 'in' CHECK (dir IN ('in','out')),
    farm_id      TEXT,
    contact      TEXT,
    phone        TEXT,
    handle       TEXT,
    ts           TEXT NOT NULL,
    duration     INTEGER NOT NULL DEFAULT 0,
    status       TEXT,
    text         TEXT,
    note         TEXT,
    read         INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'manual',
    external_id  TEXT,
    payload      TEXT,
    peer_key     TEXT
);
CREATE INDEX IF NOT EXISTS idx_comms_ts     ON comms (ts DESC);
CREATE INDEX IF NOT EXISTS idx_comms_farm   ON comms (farm_id);
CREATE INDEX IF NOT EXISTS idx_comms_unread ON comms (read);
CREATE INDEX IF NOT EXISTS idx_comms_seq    ON comms (seq);
-- идемпотентность webhook'ов: в SQLite был partial unique index, но для
-- ON CONFLICT (source, external_id) без WHERE в PG нужен полный уникальный
-- индекс; NULL-ы в source/external_id не конфликтуют (NULL DISTINCT в PG).
CREATE UNIQUE INDEX IF NOT EXISTS idx_comms_ext ON comms (source, external_id);

CREATE TABLE IF NOT EXISTS chat_drafts (
    peer_key TEXT PRIMARY KEY,
    draft    TEXT NOT NULL DEFAULT '',
    updated  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT '🔗',
    color       TEXT NOT NULL DEFAULT '#888',
    grp         TEXT NOT NULL DEFAULT 'Прочее',
    enabled     INTEGER NOT NULL DEFAULT 1,
    directions  TEXT NOT NULL DEFAULT '["in","out"]',
    connectors  TEXT NOT NULL DEFAULT '[]',
    meta        TEXT
);

CREATE TABLE IF NOT EXISTS channel_accounts (
    id           TEXT PRIMARY KEY,
    channel      TEXT NOT NULL,
    login        TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    farm_id      TEXT,
    token        TEXT,
    secret       TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    created_by   TEXT,
    created_at   TEXT,
    updated_at   TEXT,
    UNIQUE (channel, login)
);

CREATE TABLE IF NOT EXISTS crm_records (
    id      TEXT NOT NULL,
    coll    TEXT NOT NULL,
    data    TEXT NOT NULL,
    updated TEXT NOT NULL,
    PRIMARY KEY (coll, id)
);
CREATE INDEX IF NOT EXISTS idx_crm_coll ON crm_records (coll);

CREATE TABLE IF NOT EXISTS logistics_docs (
    id      TEXT PRIMARY KEY,
    kind    TEXT NOT NULL CHECK (kind IN ('supply','dispatch')),
    data    TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_kind ON logistics_docs (kind, updated DESC);

CREATE TABLE IF NOT EXISTS users (
    login         TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'pending',
    pw_hash       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    position      TEXT NOT NULL DEFAULT '',
    phone         TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    token_version INTEGER NOT NULL DEFAULT 0
);
