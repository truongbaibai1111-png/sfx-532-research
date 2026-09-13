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


def ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_streams", "-show_format",
        "-of", "json", str(path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    fps = None
    if video:
        raw = video.get("avg_frame_rate") or video.get("r_frame_rate")
        if raw and raw != "0/0":
            n, d = raw.split("/")
            fps = float(n) / float(d)

    duration = data.get("format", {}).get("duration")
    return {
        "duration_sec": float(duration) if duration else None,
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
