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


def synthetic_detector_test():
    sr = 16000
    x = np.zeros(sr * 2, dtype=np.float32)
    x[int(0.9 * sr):int(0.95 * sr)] = 0.8

    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "synthetic.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((x * 32767).astype(np.int16).tobytes())

        events = detect_candidates(wav_path)
        if not events or not any(e["start_sec"] <= 0.9 <= e["end_sec"] for e in events):
            raise RuntimeError("candidate detector failed synthetic transient test")
        print(f"PASS: detector found {len(events)} candidate(s) in synthetic test")


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
