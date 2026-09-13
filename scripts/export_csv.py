from pathlib import Path
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import connect
from sfx532.paths import EXPORTS

queries = {
    "videos.csv": "SELECT * FROM videos ORDER BY id",
    "event_candidates.csv": """
        SELECT c.*, v.filename
        FROM event_candidates c
        JOIN videos v ON v.id=c.video_id
        ORDER BY c.video_id, c.start_sec
    """,
    "events.csv": """
        SELECT e.*, v.filename
        FROM events e
        JOIN videos v ON v.id=e.video_id
        ORDER BY e.video_id, e.start_sec
    """,
}

with connect() as con:
    for filename, query in queries.items():
        rows = con.execute(query).fetchall()
        out = EXPORTS / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if rows:
                writer.writerow(rows[0].keys())
                writer.writerows([tuple(row) for row in rows])
        print(f"{filename}: {len(rows)} row(s)")
