from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import init_db, connect, SCHEMA_VERSION
from sfx532.detect import detect_candidates
from sfx532.media import ffprobe
from sfx532.paths import DB


def check_command(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} not found in PATH")
    subprocess.run([name, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"PASS: {name} -> {path}")


def _write_wav(path, x, sr=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def unicode_ffprobe_test():
    sr = 16000
    with tempfile.TemporaryDirectory() as td:
        media_path = Path(td) / "001_뒤통수_âm-thanh.wav"
        _write_wav(media_path, np.zeros(sr, dtype=np.float32), sr)
        meta = ffprobe(media_path)
        if meta["has_audio"] != 1:
            raise RuntimeError("ffprobe Unicode-path test did not detect audio")
        if meta["duration_sec"] is None:
            raise RuntimeError("ffprobe Unicode-path test did not return duration")
        print("PASS: ffprobe handles Unicode media filename")


def schema_test():
    required = {
        "review_score", "review_tier", "trigger_count",
        "spectral_flatness", "tonal_penalty",
    }
    with connect() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        columns = {row[1] for row in con.execute("PRAGMA table_info(event_candidates)")}
    missing = required - columns
    if version != SCHEMA_VERSION:
        raise RuntimeError(f"schema version mismatch: db={version}, code={SCHEMA_VERSION}")
    if missing:
        raise RuntimeError(f"schema migration missing columns: {sorted(missing)}")
    print(f"PASS: SQLite schema {version} includes Detector V0.2.x review fields")


def synthetic_detector_test():
    sr = 16000
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        transient = np.zeros(sr * 2, dtype=np.float32)
        transient[int(0.9 * sr):int(0.95 * sr)] = 0.8
        transient_path = td / "transient.wav"
        _write_wav(transient_path, transient, sr)
        events = detect_candidates(transient_path)
        if not events or not any(e["start_sec"] <= 0.9 <= e["end_sec"] for e in events):
            raise RuntimeError("candidate detector failed synthetic transient test")
        if not all(e["detector"].endswith("v0.2.1") for e in events):
            raise RuntimeError("Detector V0.2.1 identifier missing")
        if not all(e["review_tier"] in {"PRIMARY", "SECONDARY"} for e in events):
            raise RuntimeError("Detector V0.2.1 review tier missing")
        if any(float(e["tonal_penalty"]) != 0.0 for e in events):
            raise RuntimeError("V0.2.1 production config/test path must not apply tonal penalty")
        print(f"PASS: Detector V0.2.1 found {len(events)} candidate(s) around synthetic transient")

        silence_path = td / "silence.wav"
        _write_wav(silence_path, np.zeros(sr * 3, dtype=np.float32), sr)
        silence_events = detect_candidates(silence_path)
        if silence_events:
            raise RuntimeError("silence must not become an event candidate")
        print("PASS: silence produces no candidate")

        # Two sub-peaks from essentially the same hit should not explode into
        # many fragments.
        double_hit = np.zeros(sr * 2, dtype=np.float32)
        double_hit[int(0.80 * sr):int(0.83 * sr)] = 0.9
        double_hit[int(0.94 * sr):int(0.97 * sr)] = 0.7
        double_path = td / "double_hit.wav"
        _write_wav(double_path, double_hit, sr)
        clustered = detect_candidates(double_path)
        if not clustered:
            raise RuntimeError("duplicate-fragment cluster test produced no candidate")
        if len(clustered) > 2:
            raise RuntimeError("nearby duplicate fragments were not controlled")
        print("PASS: nearby duplicate fragments are controlled")

        # Three distinct cartoon cues spaced hundreds of milliseconds apart must
        # not chain into one multi-second candidate just because pre/post padding
        # makes their intervals overlap.
        separate = np.zeros(sr * 3, dtype=np.float32)
        for t, amp in [(0.55, 0.9), (1.05, 0.75), (1.55, 0.85)]:
            separate[int(t * sr):int((t + 0.035) * sr)] = amp
        separate_path = td / "separate_cues.wav"
        _write_wav(separate_path, separate, sr)
        cues = detect_candidates(separate_path)
        if len(cues) < 2:
            raise RuntimeError("distinct cues were chain-merged too aggressively")
        if max(float(e["end_sec"] - e["start_sec"]) for e in cues) > 2.0:
            raise RuntimeError("synthetic cue event became implausibly long")
        print("PASS: distinct nearby cues do not chain-merge")


def main():
    print("SFX 532 Research — self test")
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10+ is required")

    check_command("ffmpeg")
    check_command("ffprobe")

    init_db()
    if not DB.exists():
        raise RuntimeError("SQLite database was not created")
    print(f"PASS: SQLite -> {DB}")
    schema_test()

    unicode_ffprobe_test()
    synthetic_detector_test()
    print("\nALL CORE CHECKS PASSED")


if __name__ == "__main__":
    main()
