import sqlite3
from .paths import DB

SCHEMA_VERSION = 3

SCHEMA = r'''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    relpath TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL DEFAULT 0,
    duration_sec REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    has_audio INTEGER NOT NULL DEFAULT 0,
    ingest_status TEXT NOT NULL DEFAULT 'INGESTED',
    process_status TEXT NOT NULL DEFAULT 'PENDING',
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    error TEXT,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS event_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    peak_sec REAL,
    score REAL,
    review_score REAL,
    review_tier TEXT NOT NULL DEFAULT 'PRIMARY',
    trigger_count INTEGER NOT NULL DEFAULT 1,
    spectral_flatness REAL,
    tonal_penalty REAL NOT NULL DEFAULT 0,
    detector TEXT NOT NULL,
    audio_clip_relpath TEXT,
    video_clip_relpath TEXT,
    frame_before_relpath TEXT,
    frame_peak_relpath TEXT,
    frame_after_relpath TEXT,
    review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    candidate_id INTEGER,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    actor TEXT,
    action_vi TEXT,
    action_en TEXT,
    motion_phase TEXT,
    material TEXT,
    emotion TEXT,
    sound_role TEXT,
    heard_description TEXT,
    creative_suggestion TEXT,
    keywords_vi TEXT,
    keywords_en TEXT,
    confidence REAL,
    evidence_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY(candidate_id) REFERENCES event_candidates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sound_layers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    layer_order INTEGER NOT NULL,
    layer_type TEXT,
    heard INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    search_query_en TEXT,
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    title TEXT,
    provider TEXT,
    page_url TEXT,
    creator TEXT,
    license TEXT,
    commercial_use INTEGER,
    attribution_required INTEGER,
    credit_text TEXT,
    checked_date TEXT,
    availability_status TEXT,
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_candidates_video ON event_candidates(video_id);
CREATE INDEX IF NOT EXISTS idx_events_video ON events(video_id);
CREATE INDEX IF NOT EXISTS idx_events_action_vi ON events(action_vi);
CREATE INDEX IF NOT EXISTS idx_events_action_en ON events(action_en);
'''


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _columns(con, table):
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(con, table, column_name, declaration):
    if column_name not in _columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {declaration}")


def _migrate_additive(con):
    # All migrations are additive so old research is never deleted by an update.
    _ensure_column(con, "videos", "mtime_ns", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "event_candidates", "video_clip_relpath", "TEXT")
    _ensure_column(con, "event_candidates", "frame_before_relpath", "TEXT")
    _ensure_column(con, "event_candidates", "frame_peak_relpath", "TEXT")
    _ensure_column(con, "event_candidates", "frame_after_relpath", "TEXT")

    # Schema 3: Detector V0.2 keeps a high-recall candidate layer but marks
    # which candidates deserve expensive review artifacts.
    _ensure_column(con, "event_candidates", "review_score", "REAL")
    _ensure_column(con, "event_candidates", "review_tier", "TEXT NOT NULL DEFAULT 'PRIMARY'")
    _ensure_column(con, "event_candidates", "trigger_count", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(con, "event_candidates", "spectral_flatness", "REAL")
    _ensure_column(con, "event_candidates", "tonal_penalty", "REAL NOT NULL DEFAULT 0")


def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        current = con.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than this tool supports ({SCHEMA_VERSION})."
            )

        # First ensure base tables exist. Do not create indexes that reference
        # new columns until after the additive column migration below.
        con.executescript(SCHEMA)
        _migrate_additive(con)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_tier "
            "ON event_candidates(video_id, review_tier)"
        )
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
