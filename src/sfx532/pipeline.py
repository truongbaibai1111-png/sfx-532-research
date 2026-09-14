import json
import shutil

from .paths import RAW, AUDIO, EVENTS, CONFIG
from .db import connect, init_db
from .media import (
    extract_audio,
    extract_audio_clip,
    extract_video_clip,
    extract_frame,
)
from .detect import detect_candidates


PROTECTED_STATES = {"RESEARCHED", "INDEXED", "COMPLETE"}


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


def _clamp_frame_time(sec: float, duration_sec):
    sec = max(0.0, float(sec))
    if duration_sec is None:
        return sec
    return min(sec, max(0.0, float(duration_sec) - 0.01))


def _apply_review_guards(event, video_duration, review_cfg):
    event = dict(event)
    tier = event.get("review_tier", "PRIMARY")

    end_guard_sec = float(review_cfg.get("end_guard_sec", 0.0) or 0.0)
    force_last = bool(review_cfg.get("force_last_seconds_secondary", False))
    if force_last and video_duration and end_guard_sec > 0:
        remaining = float(video_duration) - float(event["peak_sec"])
        if remaining <= end_guard_sec:
            # Do not delete end-card candidates. Keep them as metadata-only
            # SECONDARY items so a genuine final action can still be recovered.
            tier = "SECONDARY"

    event["review_tier"] = tier
    return event


def process_video(video_id: int) -> dict:
    # Running a detector upgrade must also apply additive DB migrations.
    init_db()
    cfg = load_config()
    video_row = get_video(video_id)
    video_path = RAW / video_row["relpath"]

    if video_row["ingest_status"] == "INVALID" or video_row["process_status"] == "INVALID":
        raise RuntimeError(f"video_id={video_id} is marked INVALID; fix/replace the source file first")

    if video_row["process_status"] in PROTECTED_STATES:
        raise RuntimeError(
            f"video_id={video_id} is already {video_row['process_status']}; "
            "candidate regeneration is blocked to protect reviewed research"
        )

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
        detected = detect_candidates(wav_path, **cfg["event"])
        candidates = [
            _apply_review_guards(
                event,
                video_row["duration_sec"],
                cfg.get("review", {}),
            )
            for event in detected
        ]

        event_dir = EVENTS / f"video_{video_id:04d}"
        if event_dir.exists():
            shutil.rmtree(event_dir)
        event_dir.mkdir(parents=True, exist_ok=True)

        primary_count = 0
        secondary_count = 0

        with connect() as con:
            con.execute("DELETE FROM event_candidates WHERE video_id=?", (video_id,))

            for index, event in enumerate(candidates, start=1):
                tier = event.get("review_tier", "PRIMARY")
                if tier == "PRIMARY":
                    primary_count += 1
                else:
                    secondary_count += 1

                audio_rel = video_rel = before_rel = peak_rel = after_rel = None

                # Expensive media packaging is only for the review-ready tier.
                # SECONDARY candidates remain queryable in SQLite with their
                # timestamps and features, preserving recall without file spam.
                if tier == "PRIMARY":
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

                    duration = video_row["duration_sec"]
                    before_sec = _clamp_frame_time(event["start_sec"] - 0.15, duration)
                    peak_sec = _clamp_frame_time(event["peak_sec"], duration)
                    after_sec = _clamp_frame_time(event["end_sec"] + 0.10, duration)

                    extract_frame(video_path, before_sec, frame_before)
                    extract_frame(video_path, peak_sec, frame_peak)
                    extract_frame(video_path, after_sec, frame_after)

                    audio_rel = _data_relpath(audio_clip)
                    video_rel = _data_relpath(video_clip)
                    before_rel = _data_relpath(frame_before)
                    peak_rel = _data_relpath(frame_peak)
                    after_rel = _data_relpath(frame_after)

                con.execute(
                    """
                    INSERT INTO event_candidates
                    (video_id,start_sec,end_sec,peak_sec,score,review_score,review_tier,
                     trigger_count,spectral_flatness,tonal_penalty,detector,
                     audio_clip_relpath,video_clip_relpath,
                     frame_before_relpath,frame_peak_relpath,frame_after_relpath)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        video_id,
                        event["start_sec"],
                        event["end_sec"],
                        event["peak_sec"],
                        event["score"],
                        event.get("review_score"),
                        tier,
                        event.get("trigger_count", 1),
                        event.get("spectral_flatness"),
                        event.get("tonal_penalty", 0.0),
                        event["detector"],
                        audio_rel,
                        video_rel,
                        before_rel,
                        peak_rel,
                        after_rel,
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
            "primary": primary_count,
            "secondary": secondary_count,
            "artifacts_generated": primary_count,
            "detector": "V0.2",
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
