import wave
import numpy as np


def _read_pcm16_mono(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        if sw != 2:
            raise ValueError("Detector V0.2.1 expects PCM16 WAV")
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
    spectral_flatness = np.ones(len(starts), dtype=np.float32)
    window = np.hanning(win).astype(np.float32)
    previous_mag = None

    for i, start in enumerate(starts):
        frame = x[start:start + win]
        if len(frame) < win:
            frame = np.pad(frame, (0, win - len(frame)))

        rms[i] = np.sqrt(np.mean(frame * frame) + 1e-12)

        mag = np.abs(np.fft.rfft(frame * window)).astype(np.float32)
        power = mag * mag + 1e-12
        spectral_flatness[i] = float(
            np.exp(np.mean(np.log(power))) / (np.mean(power) + 1e-12)
        )

        norm = float(np.linalg.norm(mag) + 1e-8)
        mag_norm = mag / norm
        if previous_mag is not None:
            positive_change = np.maximum(mag_norm - previous_mag, 0.0)
            spectral_flux[i] = float(np.sqrt(np.sum(positive_change * positive_change)))
        previous_mag = mag_norm

    return starts, rms, spectral_flux, spectral_flatness


def _merge_intervals(active_idx, hop_ms, merge_gap_ms):
    if len(active_idx) == 0:
        return []

    intervals = []
    first = previous = int(active_idx[0])
    merge_frames = max(1, int(round(merge_gap_ms / hop_ms)))

    for idx in active_idx[1:]:
        idx = int(idx)
        if idx - previous <= merge_frames:
            previous = idx
        else:
            intervals.append((first, previous))
            first = previous = idx
    intervals.append((first, previous))
    return intervals


def _cluster_candidates(candidates, cluster_peak_ms, cluster_max_span_ms):
    """Merge only obvious duplicate fragments around nearly the same audio peak.

    V0.2 used padded interval gaps as one of the merge conditions. Because every
    candidate already has pre/post roll, neighbouring but distinct cues often
    overlapped after padding and could chain into multi-second research events.

    V0.2.1 deliberately ignores padded interval overlap. Two fragments may join
    only when their representative peaks are very close AND the resulting group
    stays below a hard maximum span. This favors event granularity over aggressive
    compression; weak/duplicate fragments are still retained if uncertain.
    """
    if not candidates:
        return []

    peak_limit = float(cluster_peak_ms) / 1000.0
    max_span = float(cluster_max_span_ms) / 1000.0
    ordered = sorted(candidates, key=lambda e: (e["peak_sec"], e["start_sec"]))
    groups = [[ordered[0]]]

    for event in ordered[1:]:
        group = groups[-1]
        prev = group[-1]
        peak_gap = float(event["peak_sec"]) - float(prev["peak_sec"])
        proposed_start = min(float(e["start_sec"]) for e in group + [event])
        proposed_end = max(float(e["end_sec"]) for e in group + [event])
        proposed_span = proposed_end - proposed_start

        if peak_gap <= peak_limit and proposed_span <= max_span:
            group.append(event)
        else:
            groups.append([event])

    merged = []
    for group in groups:
        strongest = max(group, key=lambda e: float(e["score"]))
        flatness_values = [float(e["spectral_flatness"]) for e in group]
        merged.append({
            "start_sec": round(min(float(e["start_sec"]) for e in group), 3),
            "end_sec": round(max(float(e["end_sec"]) for e in group), 3),
            "peak_sec": round(float(strongest["peak_sec"]), 3),
            "score": round(max(float(e["score"]) for e in group), 4),
            "spectral_flatness": round(float(np.median(flatness_values)), 4),
            "trigger_count": int(sum(int(e.get("trigger_count", 1)) for e in group)),
        })
    return merged


def detect_candidates(
    wav_path,
    window_ms=25,
    hop_ms=10,
    min_event_ms=80,
    max_event_ms=3500,
    merge_gap_ms=160,
    cluster_peak_ms=180,
    cluster_max_span_ms=1500,
    energy_percentile=85,
    noise_percentile=20,
    noise_margin_db=10.0,
    absolute_floor_db=-72.0,
    onset_z=3.0,
    spectral_flux_z=3.3,
    pre_roll_ms=120,
    post_roll_ms=220,
    tonal_flatness_threshold=0.0,
    tonal_penalty_max=0.0,
    primary_score_threshold=3.5,
):
    sr, x = _read_pcm16_mono(wav_path)
    if len(x) == 0:
        return []

    starts, rms, spectral_flux, spectral_flatness = _features(
        x, sr, window_ms, hop_ms
    )
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

    # Sustained energy alone is not enough. A cue needs a local change in level
    # or spectrum; this prevents a loud music bed from becoming one giant event.
    moderate_change = (
        (onset_score >= onset_z * 0.60)
        | (flux_score >= spectral_flux_z * 0.60)
    )
    active = (
        ((log_energy >= energy_threshold) & moderate_change)
        | (onset_score >= onset_z)
        | (flux_score >= spectral_flux_z)
    )

    active_idx = np.flatnonzero(active)
    if len(active_idx) == 0:
        return []

    intervals = _merge_intervals(active_idx, hop_ms, merge_gap_ms)
    raw_candidates = []
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
            flatness = float(np.median(spectral_flatness[ia:ib])) if ib > ia else 1.0

            raw_candidates.append({
                "start_sec": float(chunk_start),
                "end_sec": float(chunk_end),
                "peak_sec": float(peak_sec),
                "score": float(score),
                "spectral_flatness": flatness,
                "trigger_count": 1,
            })

    clustered = _cluster_candidates(
        raw_candidates,
        cluster_peak_ms=cluster_peak_ms,
        cluster_max_span_ms=cluster_max_span_ms,
    )

    output = []
    for event in clustered:
        flatness = float(event["spectral_flatness"])

        # Kept as an optional hook, but disabled in the production config until
        # calibrated on a larger labelled set. Short-time flatness alone proved
        # too broad on video 001 and must not silently demote every event.
        if tonal_flatness_threshold > 0 and tonal_penalty_max > 0 and flatness < tonal_flatness_threshold:
            tonal_ratio = min(
                1.0,
                max(0.0, (tonal_flatness_threshold - flatness) / tonal_flatness_threshold),
            )
            tonal_penalty = tonal_ratio * float(tonal_penalty_max)
        else:
            tonal_penalty = 0.0

        review_score = max(0.0, float(event["score"]) - tonal_penalty)
        review_tier = "PRIMARY" if review_score >= primary_score_threshold else "SECONDARY"

        output.append({
            "start_sec": round(float(event["start_sec"]), 3),
            "end_sec": round(float(event["end_sec"]), 3),
            "peak_sec": round(float(event["peak_sec"]), 3),
            "score": round(float(event["score"]), 4),
            "review_score": round(review_score, 4),
            "review_tier": review_tier,
            "trigger_count": int(event["trigger_count"]),
            "spectral_flatness": round(flatness, 4),
            "tonal_penalty": round(float(tonal_penalty), 4),
            "detector": "energy_onset_flux_cluster_v0.2.1",
        })

    return output
