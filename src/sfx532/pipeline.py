import json
from .paths import RAW, AUDIO, EVENTS, CONFIG
from .db import connect
from .media import extract_audio, extract_audio_clip
from .detect import detect_candidates


def load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def get_video(video_id: int) -> dict:
    with connect() as con:
        row = con.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown video_id={video_id}")
        return dict(row)


def process_video(video_id: int) -> dict:
    cfg = load_config()
    video_row = get_video(video_id)
    video_path = RAW / video_row["relpath"]

    if not video_path.exists():
        raise FileNotFoundError(video_path)

    if not video_row["has_audio"]:
        with connect() as con:
            con.execute(
                "UPDATE videos SET process_status='NO_AUDIO', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (video_id,),
            )
        return {"video_id": video_id, "status": "NO_AUDIO", "candidates": 0}

    wav_path = AUDIO / f"video_{video_id:04d}.wav"
    run_id = None

    try:
        with connect() as con:
            con.execute(
                "UPDATE videos SET process_status='RUNNING', error=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (video_id,),
            )
            cur = con.execute(
                "INSERT INTO pipeline_runs(video_id,stage,status,pipeline_version) VALUES (?,?,?,?)",
                (video_id, "AUDIO_AND_CANDIDATES", "RUNNING", cfg["pipeline_version"]),
            )
            run_id = cur.lastrowid

        extract_audio(video_path, wav_path, cfg["sample_rate"])
        candidates = detect_candidates(wav_path, **cfg["event"])

        event_dir = EVENTS / f"video_{video_id:04d}"
        event_dir.mkdir(parents=True, exist_ok=True)

        with connect() as con:
            con.execute("DELETE FROM event_candidates WHERE video_id=?", (video_id,))

            for index, event in enumerate(candidates, start=1):
                clip_path = event_dir / f"event_{index:04d}.wav"
                extract_audio_clip(
                    video_path,
                    event["start_sec"],
                    event["end_sec"],
                    clip_path,
                    cfg["sample_rate"],
                )
                relpath = clip_path.relative_to(RAW.parent).as_posix()
                con.execute(
                    """
                    INSERT INTO event_candidates
                    (video_id,start_sec,end_sec,peak_sec,score,detector,audio_clip_relpath)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        video_id,
                        event["start_sec"],
                        event["end_sec"],
                        event["peak_sec"],
                        event["score"],
                        event["detector"],
                        relpath,
                    ),
                )

            con.execute(
                "UPDATE pipeline_runs SET status='PASS', finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (run_id,),
            )
            con.execute(
                "UPDATE videos SET process_status='CANDIDATES_READY', error=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (video_id,),
            )

        return {
            "video_id": video_id,
            "status": "CANDIDATES_READY",
            "candidates": len(candidates),
        }

    except Exception as exc:
        with connect() as con:
            con.execute(
                "UPDATE videos SET process_status='FAILED', error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (repr(exc), video_id),
            )
            if run_id is not None:
                con.execute(
                    "UPDATE pipeline_runs SET status='FAIL', error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                    (repr(exc), run_id),
                )
        raise
