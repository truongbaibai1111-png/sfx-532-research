from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import init_db
from sfx532.detect import detect_candidates
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
        print(f"PASS: detector found {len(events)} candidate(s) around synthetic transient")

        silence_path = td / "silence.wav"
        _write_wav(silence_path, np.zeros(sr * 3, dtype=np.float32), sr)
        silence_events = detect_candidates(silence_path)
        if silence_events:
            raise RuntimeError("silence must not become an event candidate")
        print("PASS: silence produces no candidate")


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

    synthetic_detector_test()
    print("\nALL CORE CHECKS PASSED")


if __name__ == "__main__":
    main()
