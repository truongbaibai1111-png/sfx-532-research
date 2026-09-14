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
        assert all(event["detector"].endswith("v0.2") for event in events)
        assert all(event["review_tier"] in {"PRIMARY", "SECONDARY"} for event in events)


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

        assert len(events) <= 1


def test_nearby_transient_fragments_cluster_into_one_research_event():
    sr = 16000
    x = np.zeros(sr * 2, dtype=np.float32)
    x[int(0.80 * sr):int(0.83 * sr)] = 0.9
    x[int(0.94 * sr):int(0.97 * sr)] = 0.7

    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "double_hit.wav"
        _write_wav(wav_path, x, sr)
        events = detect_candidates(wav_path)

        covering = [e for e in events if e["start_sec"] <= 0.80 and e["end_sec"] >= 0.94]
        assert covering, events
        assert max(e["trigger_count"] for e in covering) >= 1


def test_tonal_feature_is_recorded_for_ranking_not_hard_deleted():
    sr = 16000
    t = np.arange(sr * 2) / sr
    x = np.zeros(sr * 2, dtype=np.float32)
    start = int(0.75 * sr)
    end = int(1.15 * sr)
    x[start:end] = 0.5 * np.sin(2 * np.pi * 880 * t[:end-start])

    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "tonal_cue.wav"
        _write_wav(wav_path, x, sr)
        events = detect_candidates(wav_path)

        assert events
        assert all("spectral_flatness" in e for e in events)
        assert all("tonal_penalty" in e for e in events)
