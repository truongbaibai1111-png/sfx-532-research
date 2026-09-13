import json
import shutil

from .paths import RAW, AUDIO, EVENTS, CONFIG
from .db import connect
from .media import (
    extract_audio,
    extract_audio_clip,
    extract_video_clip,
    extract_frame,
)
from .detect import detect_candidates


def load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def get_video(video_id: int) -> dict:
    with connect() as con:
        row = con.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown video_id={video_id}")
        return dict(row)


def _data_relpath(path):
    return path.relative_to(RAW.parent).as_posix()


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
        if event_dir.exists():
            shutil.rmtree(event_dir)
        event_dir.mkdir(parents=True, exist_ok=True)

        with connect() as con:
            con.execute("DELETE FROM event_candidates WHERE video_id=?", (video_id,))

            for index, event in enumerate(candidates, start=1):
                base = f"event_{index:04d}"
                audio_clip = event_dir / f"{base}.wav"
                video_clip = event_dir / f"{base}.mp4"
                frame_before = event_dir / f"{base}_before.jpg"
                frame_peak = event_dir / f"{base}_peak.jpg"
                frame_after = event_dir / f"{base}_after.jpg"

                extract_audio_clip(
                    video_path,
                    event["start_sec"],
                    event["end_sec"],
                    audio_clip,
                    cfg["sample_rate"],
                )
                extract_video_clip(
                    video_path,
                    event["start_sec"],
                    event["end_sec"],
                    video_clip,
                )

                # Visual context: one frame before onset, one at the energy peak,
                # and one immediately after the candidate. These are evidence only;
                # they do not classify the action by themselves.
                extract_frame(video_path, max(0.0, event["start_sec"] - 0.15), frame_before)
                extract_frame(video_path, event["peak_sec"], frame_peak)
                extract_frame(video_path, event["end_sec"] + 0.10, frame_after)

                con.execute(
                    """
                    INSERT INTO event_candidates
                    (video_id,start_sec,end_sec,peak_sec,score,detector,
                     audio_clip_relpath,video_clip_relpath,
                     frame_before_relpath,frame_peak_relpath,frame_after_relpath)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        video_id,
                        event["start_sec"],
                        event["end_sec"],
                        event["peak_sec"],
                        event["score"],
                        event["detector"],
                        _data_relpath(audio_clip),
                        _data_relpath(video_clip),
                        _data_relpath(frame_before),
                        _data_relpath(frame_peak),
                        _data_relpath(frame_after),
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
