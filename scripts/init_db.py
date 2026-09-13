from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import init_db
from sfx532.paths import DB

init_db()
print(f"OK: database initialized at {DB}")
