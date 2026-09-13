from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.paths import RAW
from sfx532.db import init_db, connect
from sfx532.media import VIDEO_EXTS, sha256_file, ffprobe

init_db()
videos = sorted(
    p for p in RAW.rglob("*")
    if p.is_file() and p.suffix.lower() in VIDEO_EXTS
)

print(f"Found {len(videos)} video(s) in {RAW}")

with connect() as con:
    for index, path in enumerate(videos, start=1):
        rel = path.relative_to(RAW).as_posix()
        sha = sha256_file(path)
        meta = ffprobe(path)
        old = con.execute("SELECT * FROM videos WHERE relpath=?", (rel,)).fetchone()

        if old and old["sha256"] != sha:
            con.execute("DELETE FROM event_candidates WHERE video_id=?", (old["id"],))
            con.execute(
                """
                UPDATE videos
                SET filename=?, sha256=?, size_bytes=?, duration_sec=?, width=?, height=?,
                    fps=?, has_audio=?, ingest_status='INGESTED', process_status='PENDING',
                    error=NULL, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    path.name,
                    sha,
                    path.stat().st_size,
                    meta["duration_sec"],
                    meta["width"],
                    meta["height"],
                    meta["fps"],
                    meta["has_audio"],
                    old["id"],
                ),
            )
            status = "CHANGED"
        elif old:
            status = "UNCHANGED"
        else:
            con.execute(
                """
                INSERT INTO videos
                (filename,relpath,sha256,size_bytes,duration_sec,width,height,fps,has_audio)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    path.name,
                    rel,
                    sha,
                    path.stat().st_size,
                    meta["duration_sec"],
                    meta["width"],
                    meta["height"],
                    meta["fps"],
                    meta["has_audio"],
                ),
            )
            status = "NEW"

        print(f"[{index}/{len(videos)}] {status}: {rel}")

print("Scan complete.")
