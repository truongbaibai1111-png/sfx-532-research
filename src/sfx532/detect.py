import wave
import numpy as np


def _read_pcm16_mono(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        if sw != 2:
            raise ValueError("Detector V0.1 expects PCM16 WAV")
        raw = w.readframes(w.getnframes())

    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return sr, x


def detect_candidates(
    wav_path,
    window_ms=25,
    hop_ms=10,
    min_event_ms=80,
    max_event_ms=6000,
    merge_gap_ms=120,
    energy_percentile=82,
    onset_z=2.8,
    pre_roll_ms=120,
    post_roll_ms=220,
):
    sr, x = _read_pcm16_mono(wav_path)
    if len(x) == 0:
        return []

    win = max(8, int(sr * window_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    starts = np.arange(0, max(1, len(x) - win + 1), hop)

    rms = np.array([
        np.sqrt(np.mean(x[s:s + win] ** 2) + 1e-12)
        for s in starts
    ], dtype=np.float32)

    log_energy = 20.0 * np.log10(rms + 1e-7)
    delta = np.diff(log_energy, prepend=log_energy[0])

    median = float(np.median(delta))
    mad = float(np.median(np.abs(delta - median)) + 1e-6)
    z = (delta - median) / (1.4826 * mad)

    energy_threshold = float(np.percentile(log_energy, energy_percentile))
    active = (log_energy >= energy_threshold) | (z >= onset_z)
    active_idx = np.flatnonzero(active)
    if len(active_idx) == 0:
        return []

    intervals = []
    first = previous = int(active_idx[0])
    merge_frames = max(1, int(merge_gap_ms / hop_ms))

    for idx in active_idx[1:]:
        idx = int(idx)
        if idx - previous <= merge_frames:
            previous = idx
        else:
            intervals.append((first, previous))
            first = previous = idx
    intervals.append((first, previous))

    output = []
    audio_duration = len(x) / sr

    for left, right in intervals:
        start = max(0.0, left * hop_ms / 1000 - pre_roll_ms / 1000)
        end = min(
            audio_duration,
            (right * hop_ms + window_ms) / 1000 + post_roll_ms / 1000,
        )
        duration_ms = (end - start) * 1000
        if duration_ms < min_event_ms:
            continue

        if duration_ms > max_event_ms:
            chunks = []
            cursor = start
            while cursor < end:
                chunks.append((cursor, min(end, cursor + max_event_ms / 1000)))
                cursor += max_event_ms / 1000
        else:
            chunks = [(start, end)]

        for chunk_start, chunk_end in chunks:
            ia = max(0, int(chunk_start * 1000 / hop_ms))
            ib = min(len(log_energy), max(ia + 1, int(chunk_end * 1000 / hop_ms)))
            local_energy = log_energy[ia:ib]
            peak_i = ia + int(np.argmax(local_energy))
            peak_sec = peak_i * hop_ms / 1000
            score = float(np.max(z[ia:ib])) if ib > ia else 0.0

            output.append({
                "start_sec": round(chunk_start, 3),
                "end_sec": round(chunk_end, 3),
                "peak_sec": round(peak_sec, 3),
                "score": round(score, 4),
                "detector": "energy_onset_v0.1",
            })

    return output
