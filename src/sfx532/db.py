import sqlite3
from .paths import DB

SCHEMA = r'''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    relpath TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
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
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL
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


def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
