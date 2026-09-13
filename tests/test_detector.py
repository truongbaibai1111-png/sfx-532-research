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


def test_silence_does_not_become_one_large_event():
    sr = 16000
    x = np.zeros(sr * 3, dtype=np.float32)

    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "silence.wav"
        _write_wav(wav_path, x, sr)
        events = detect_candidates(wav_path)

        assert events == []


def test_steady_quiet_tone_is_not_selected_only_by_percentile():
    sr = 16000
    t = np.arange(sr * 2) / sr
    x = (0.001 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "tone.wav"
        _write_wav(wav_path, x, sr)
        events = detect_candidates(wav_path)

        # The detector is intended to find change/cues, not mark a constant quiet bed.
        assert len(events) <= 1
