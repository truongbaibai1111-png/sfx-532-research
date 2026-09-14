from pathlib import Path
import hashlib
import json
import subprocess

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _decode_process_bytes(data: bytes) -> str:
    """Decode FFmpeg-family output deterministically on Windows.

    FFmpeg/FFprobe JSON and diagnostics are UTF-8 in our workflow, but
    subprocess(text=True) otherwise asks Python to use the active Windows
    ANSI code page (for example cp1252). A Unicode media filename can then
    crash the reader thread before we ever see ffprobe's JSON. Decode bytes
    ourselves and replace only malformed diagnostic bytes if any exist.
    """
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


def ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_streams", "-show_format",
        "-of", "json", str(path),
    ]

    # Deliberately capture BYTES. Do not use text=True here: on Windows it
    # may decode with cp1252/cp1258 and fail on Korean/Japanese/etc filenames.
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    stdout = _decode_process_bytes(p.stdout)
    stderr = _decode_process_bytes(p.stderr)

    if p.returncode != 0:
        detail = stderr.strip() or f"ffprobe exited with code {p.returncode}"
        raise RuntimeError(f"ffprobe failed for {path.name!r}: {detail}")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        preview = stdout[:500].replace("\n", " ")
        raise RuntimeError(
            f"ffprobe returned invalid JSON for {path.name!r}: {preview!r}"
        ) from exc

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    fps = None
    if video:
        raw = video.get("avg_frame_rate") or video.get("r_frame_rate")
        if raw and raw != "0/0":
            try:
                n, d = raw.split("/")
                d_value = float(d)
                if d_value != 0:
                    fps = float(n) / d_value
            except (ValueError, ZeroDivisionError):
                fps = None

    duration = data.get("format", {}).get("duration")
    try:
        duration_sec = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_sec = None

    return {
        "duration_sec": duration_sec,
        "width": int(video["width"]) if video and video.get("width") else None,
        "height": int(video["height"]) if video and video.get("height") else None,
        "fps": fps,
        "has_audio": 1 if audio else 0,
    }


def extract_audio(video: Path, out_wav: Path, sample_rate: int = 16000) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", str(out_wav),
    ]
    subprocess.run(cmd, check=True)


def extract_audio_clip(video: Path, start: float, end: float, out_wav: Path, sample_rate: int = 16000) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.01, end - start)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{duration:.3f}",
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", str(out_wav),
    ]
    subprocess.run(cmd, check=True)


def extract_video_clip(video: Path, start: float, end: float, out_mp4: Path) -> None:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.05, end - start)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{duration:.3f}",
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(out_mp4),
    ]
    subprocess.run(cmd, check=True)


def extract_frame(video: Path, sec: float, out_jpg: Path) -> None:
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, sec):.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(out_jpg),
    ]
    subprocess.run(cmd, check=True)
