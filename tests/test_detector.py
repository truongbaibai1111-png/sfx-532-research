import tempfile
import wave
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.detect import detect_candidates


def _write_wav(path, x, sr=16000):
    y = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def test_detects_short_transient():
    sr = 16000
    x = np.zeros(sr * 2, dtype=np.float32)
    x[int(0.9 * sr):int(0.95 * sr)] = 0.8

    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "transient.wav"
        _write_wav(wav_path, x, sr)
        events = detect_candidates(wav_path)

        assert events
        assert any(event["start_sec"] <= 0.9 <= event["end_sec"] for event in events)
