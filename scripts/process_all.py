from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import connect
from sfx532.pipeline import process_video

with connect() as con:
    rows = con.execute(
        """
        SELECT id, filename, process_status
        FROM videos
        WHERE process_status IN ('PENDING','FAILED')
        ORDER BY id
        """
    ).fetchall()

print(f"Queue: {len(rows)} video(s)")
print("WARNING: only use this after the detector has been validated on a small representative test set.")

for index, row in enumerate(rows, start=1):
    try:
        result = process_video(row["id"])
        print(f"[{index}/{len(rows)}] PASS {row['filename']}: {result}")
    except Exception as exc:
        print(f"[{index}/{len(rows)}] FAIL {row['filename']}: {exc!r}")
