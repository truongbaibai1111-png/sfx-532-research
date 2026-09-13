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


def _robust_z(values):
    values = np.asarray(values, dtype=np.float32)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)) + 1e-6)
    return (values - median) / (1.4826 * mad)


def _features(x, sr, window_ms, hop_ms):
    win = max(16, int(sr * window_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    starts = np.arange(0, max(1, len(x) - win + 1), hop)

    rms = np.empty(len(starts), dtype=np.float32)
    spectral_flux = np.zeros(len(starts), dtype=np.float32)
    window = np.hanning(win).astype(np.float32)
    previous_mag = None

    for i, start in enumerate(starts):
        frame = x[start:start + win]
        if len(frame) < win:
            frame = np.pad(frame, (0, win - len(frame)))

        rms[i] = np.sqrt(np.mean(frame * frame) + 1e-12)

        mag = np.abs(np.fft.rfft(frame * window)).astype(np.float32)
        norm = float(np.linalg.norm(mag) + 1e-8)
        mag /= norm
        if previous_mag is not None:
            positive_change = np.maximum(mag - previous_mag, 0.0)
            spectral_flux[i] = float(np.sqrt(np.sum(positive_change * positive_change)))
        previous_mag = mag

    return starts, rms, spectral_flux


def detect_candidates(
    wav_path,
    window_ms=25,
    hop_ms=10,
    min_event_ms=80,
    max_event_ms=6000,
    merge_gap_ms=120,
    energy_percentile=82,
    noise_percentile=20,
    noise_margin_db=8.0,
    absolute_floor_db=-75.0,
    onset_z=2.8,
    spectral_flux_z=3.2,
    pre_roll_ms=120,
    post_roll_ms=220,
):
    sr, x = _read_pcm16_mono(wav_path)
    if len(x) == 0:
        return []

    starts, rms, spectral_flux = _features(x, sr, window_ms, hop_ms)
    log_energy = 20.0 * np.log10(rms + 1e-7)

    energy_delta = np.diff(log_energy, prepend=log_energy[0])
    onset_score = _robust_z(energy_delta)
    flux_score = _robust_z(spectral_flux)

    noise_floor = float(np.percentile(log_energy, noise_percentile))
    percentile_threshold = float(np.percentile(log_energy, energy_percentile))
    energy_threshold = max(
        percentile_threshold,
        noise_floor + float(noise_margin_db),
        float(absolute_floor_db),
    )

    # Three complementary triggers:
    # 1) sustained energy clearly above the track's noise/background floor,
    # 2) sudden broadband level increase,
    # 3) sudden spectral/timbral change even when total loudness barely changes.
    active = (
        (log_energy >= energy_threshold)
        | (onset_score >= onset_z)
        | (flux_score >= spectral_flux_z)
    )

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

            local_onset = float(np.max(onset_score[ia:ib])) if ib > ia else 0.0
            local_flux = float(np.max(flux_score[ia:ib])) if ib > ia else 0.0
            score = max(local_onset, local_flux)

            output.append({
                "start_sec": round(chunk_start, 3),
                "end_sec": round(chunk_end, 3),
                "peak_sec": round(peak_sec, 3),
                "score": round(score, 4),
                "detector": "energy_onset_flux_v0.1",
            })

    return output
