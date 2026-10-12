-- Runtime creates this schema in store.init(). payload is validated application JSON.
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    updated REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner);
-- payload: name, created, settings, assets (original pointer, vector paths,
-- geometry WKT, sizes, quantities, rotation lock, confirmation), best, attempts,
-- elapsed, initial_length, best_length, validation, checkpoint, snapshot.
-- Users: /data/users.json contains username => scrypt salt:hash.
