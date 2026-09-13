from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw_videos"
DERIVED = DATA / "derived"
AUDIO = DERIVED / "audio"
FRAMES = DERIVED / "frames"
EVENTS = DERIVED / "events"
DB = DATA / "db" / "sfx532.sqlite"
EXPORTS = DATA / "exports"
LOGS = ROOT / "logs"
CONFIG = ROOT / "config" / "default.json"

for p in [RAW, AUDIO, FRAMES, EVENTS, DB.parent, EXPORTS, LOGS]:
    p.mkdir(parents=True, exist_ok=True)
