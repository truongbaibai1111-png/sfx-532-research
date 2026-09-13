from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.paths import RAW, AUDIO, EVENTS
from sfx532.db import init_db, connect
from sfx532.media import VIDEO_EXTS, sha256_file, ffprobe


def invalidate_derived(con, video_id: int) -> None:
    # A changed raw file invalidates every conclusion derived from the old bytes.
    con.execute("DELETE FROM events WHERE video_id=?", (video_id,))
    con.execute("DELETE FROM event_candidates WHERE video_id=?", (video_id,))

    wav = AUDIO / f"video_{video_id:04d}.wav"
    if wav.exists():
        wav.unlink()

    event_dir = EVENTS / f"video_{video_id:04d}"
    if event_dir.exists():
        shutil.rmtree(event_dir)


def inspect_media(path: Path):
    try:
        return ffprobe(path), None
    except Exception as exc:
        return {
            "duration_sec": None,
            "width": None,
            "height": None,
            "fps": None,
            "has_audio": 0,
        }, repr(exc)


def main():
    init_db()
    videos = sorted(
        p for p in RAW.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )

    print(f"Found {len(videos)} video(s) in {RAW}")

    with connect() as con:
        for index, path in enumerate(videos, start=1):
            rel = path.relative_to(RAW).as_posix()
            stat = path.stat()
            old = con.execute("SELECT * FROM videos WHERE relpath=?", (rel,)).fetchone()

            # Fast path: unchanged size + nanosecond mtime means no expensive re-hash.
            if old and old["size_bytes"] == stat.st_size and old["mtime_ns"] == stat.st_mtime_ns:
                print(f"[{index}/{len(videos)}] UNCHANGED: {rel}")
                continue

            sha = sha256_file(path)

            # Timestamp changed but bytes did not. Keep all derived research.
            if old and old["sha256"] == sha:
                con.execute(
                    """
                    UPDATE videos
                    SET filename=?, size_bytes=?, mtime_ns=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (path.name, stat.st_size, stat.st_mtime_ns, old["id"]),
                )
                print(f"[{index}/{len(videos)}] SAME_BYTES: {rel}")
                continue

            meta, probe_error = inspect_media(path)
            ingest_status = "VALIDATED" if probe_error is None else "INVALID"
            process_status = "PENDING" if probe_error is None else "INVALID"

            if old:
                invalidate_derived(con, old["id"])
                con.execute(
                    """
                    UPDATE videos
                    SET filename=?, sha256=?, size_bytes=?, mtime_ns=?,
                        duration_sec=?, width=?, height=?, fps=?, has_audio=?,
                        ingest_status=?, process_status=?, error=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        path.name,
                        sha,
                        stat.st_size,
                        stat.st_mtime_ns,
                        meta["duration_sec"],
                        meta["width"],
                        meta["height"],
                        meta["fps"],
                        meta["has_audio"],
                        ingest_status,
                        process_status,
                        probe_error,
                        old["id"],
                    ),
                )
                status = "CHANGED" if probe_error is None else "CHANGED_INVALID"
            else:
                con.execute(
                    """
                    INSERT INTO videos
                    (filename,relpath,sha256,size_bytes,mtime_ns,duration_sec,width,height,fps,
                     has_audio,ingest_status,process_status,error)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        path.name,
                        rel,
                        sha,
                        stat.st_size,
                        stat.st_mtime_ns,
                        meta["duration_sec"],
                        meta["width"],
                        meta["height"],
                        meta["fps"],
                        meta["has_audio"],
                        ingest_status,
                        process_status,
                        probe_error,
                    ),
                )
                status = "NEW" if probe_error is None else "NEW_INVALID"

            print(f"[{index}/{len(videos)}] {status}: {rel}")
            if probe_error:
                print(f"    ffprobe error: {probe_error}")

    print("Scan complete.")


if __name__ == "__main__":
    main()
