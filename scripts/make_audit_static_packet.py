from pathlib import Path
import argparse
import csv
import math
import shutil
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import connect, init_db
from sfx532.paths import EXPORTS, RAW, AUDIO


FRAME_W = 480
FRAME_H = 270
SPEC_W = 1440
SPEC_H = 180
LABEL_H = 42
ROW_H = LABEL_H + FRAME_H + SPEC_H
ROWS_PER_SHEET = 6


def pick_indices(n, count):
    if n <= count:
        return list(range(n))
    if count <= 1:
        return [0]
    out = []
    for i in range(count):
        idx = round(i * (n - 1) / (count - 1))
        if idx not in out:
            out.append(idx)
    return out


def run(cmd):
    subprocess.run(cmd, check=True)


def extract_frame(source, sec, out_path):
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-err_detect", "ignore_err",
        "-ss", f"{max(0.0, sec):.3f}", "-i", str(source),
        "-frames:v", "1",
        "-vf",
        f"scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=decrease,"
        f"pad={FRAME_W}:{FRAME_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-q:v", "2", str(out_path),
    ])


def extract_spectrogram(wav_path, start, duration, out_path):
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}",
        "-i", str(wav_path),
        "-lavfi",
        f"showspectrumpic=s={SPEC_W}x{SPEC_H}:legend=0:color=intensity:scale=log",
        "-frames:v", "1", str(out_path),
    ])


def read_wav_pcm16_mono(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        if sw != 2:
            raise ValueError("Expected PCM16 WAV")
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return sr, x


def robust_audio_features(x, sr, start, end, peak_sec):
    ia = max(0, int(start * sr))
    ib = min(len(x), max(ia + 1, int(end * sr)))
    y = x[ia:ib]
    if len(y) < 64:
        return {
            "rms_db": -120.0,
            "crest_factor": 0.0,
            "zcr": 0.0,
            "centroid_hz": 0.0,
            "flatness": 0.0,
            "peak_prominence_db": 0.0,
            "flux_peak": 0.0,
        }

    rms = float(np.sqrt(np.mean(y * y) + 1e-12))
    peak = float(np.max(np.abs(y)) + 1e-12)
    crest = peak / max(rms, 1e-9)
    zcr = float(np.mean(np.abs(np.diff(np.signbit(y)).astype(np.float32))))

    nfft = 2048
    if len(y) < nfft:
        yy = np.pad(y, (0, nfft - len(y)))
    else:
        yy = y[:nfft]
    win = np.hanning(len(yy)).astype(np.float32)
    mag = np.abs(np.fft.rfft(yy * win)) + 1e-12
    freqs = np.fft.rfftfreq(len(yy), 1.0 / sr)
    centroid = float(np.sum(freqs * mag) / np.sum(mag))
    flatness = float(np.exp(np.mean(np.log(mag))) / np.mean(mag))

    frame = max(128, int(sr * 0.025))
    hop = max(64, int(sr * 0.010))
    starts = np.arange(0, max(1, len(y) - frame + 1), hop)
    if len(starts) == 0:
        starts = np.array([0])
    rms_frames = np.array([
        np.sqrt(np.mean(y[s:s + frame] ** 2) + 1e-12)
        for s in starts
    ], dtype=np.float32)
    db = 20.0 * np.log10(rms_frames + 1e-9)
    peak_local = peak_sec - start
    peak_idx = int(np.clip(round(peak_local * sr / hop), 0, len(db) - 1))
    median_db = float(np.median(db))
    prominence = float(db[peak_idx] - median_db)

    specs = []
    for s in starts:
        seg = y[s:s + frame]
        if len(seg) < frame:
            seg = np.pad(seg, (0, frame - len(seg)))
        sp = np.abs(np.fft.rfft(seg * np.hanning(frame)))
        specs.append(sp)
    specs = np.asarray(specs, dtype=np.float32)
    if len(specs) > 1:
        norm = specs / (np.sum(specs, axis=1, keepdims=True) + 1e-9)
        flux = np.sqrt(np.sum(np.maximum(0.0, norm[1:] - norm[:-1]) ** 2, axis=1))
        flux_peak = float(np.max(flux))
    else:
        flux_peak = 0.0

    return {
        "rms_db": round(20.0 * math.log10(rms + 1e-9), 3),
        "crest_factor": round(crest, 3),
        "zcr": round(zcr, 5),
        "centroid_hz": round(centroid, 1),
        "flatness": round(flatness, 5),
        "peak_prominence_db": round(prominence, 3),
        "flux_peak": round(flux_peak, 6),
    }


def default_font(size=18):
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", type=int, required=True)
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--context", type=float, default=3.0)
    ap.add_argument("--frame-offset", type=float, default=0.75)
    ap.add_argument(
        "--include-secondary",
        action="store_true",
        help="Sample all retained candidates. Default V0.2 behavior audits PRIMARY only.",
    )
    args = ap.parse_args()

    init_db()
    with connect() as con:
        video = con.execute("SELECT * FROM videos WHERE id=?", (args.video_id,)).fetchone()
        if not video:
            raise SystemExit(f"Unknown video_id={args.video_id}")
        if args.include_secondary:
            rows = con.execute(
                "SELECT * FROM event_candidates WHERE video_id=? ORDER BY start_sec",
                (args.video_id,),
            ).fetchall()
            audit_scope = "ALL"
        else:
            rows = con.execute(
                "SELECT * FROM event_candidates WHERE video_id=? AND review_tier='PRIMARY' ORDER BY start_sec",
                (args.video_id,),
            ).fetchall()
            audit_scope = "PRIMARY"

    if not rows:
        raise SystemExit("No candidates in selected audit scope. Run process_video.py first.")

    source = RAW / video["relpath"]
    wav_path = AUDIO / f"video_{args.video_id:04d}.wav"
    if not source.exists():
        raise SystemExit(f"Raw video not found: {source}")
    if not wav_path.exists():
        raise SystemExit(f"Analysis WAV not found: {wav_path}")

    sr, full_audio = read_wav_pcm16_mono(wav_path)
    source_duration = float(video["duration_sec"] or (len(full_audio) / sr))

    indices = pick_indices(len(rows), min(args.count, len(rows)))
    selected = [rows[i] for i in indices]

    out_dir = EXPORTS / f"audit_static_video_{args.video_id:04d}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    half = args.context / 2.0

    for sample_no, row in enumerate(selected, start=1):
        peak = float(row["peak_sec"] or row["start_sec"])
        start = max(0.0, peak - half)
        end = min(source_duration, start + args.context)
        if end - start < args.context and end >= source_duration:
            start = max(0.0, end - args.context)
        duration = max(0.2, end - start)

        before_t = max(0.0, peak - args.frame_offset)
        peak_t = peak
        after_t = min(source_duration, peak + args.frame_offset)

        base = f"s{sample_no:02d}_c{row['id']:04d}"
        before = out_dir / f"{base}_before.jpg"
        middle = out_dir / f"{base}_peak.jpg"
        after = out_dir / f"{base}_after.jpg"
        spec = out_dir / f"{base}_spec.png"

        extract_frame(source, before_t, before)
        extract_frame(source, peak_t, middle)
        extract_frame(source, after_t, after)
        extract_spectrogram(wav_path, start, duration, spec)

        features = robust_audio_features(full_audio, sr, start, end, peak)
        record = {
            "sample_no": sample_no,
            "candidate_id": int(row["id"]),
            "review_tier": row["review_tier"],
            "review_score": float(row["review_score"] or 0.0),
            "candidate_start": float(row["start_sec"]),
            "candidate_end": float(row["end_sec"]),
            "candidate_peak": peak,
            "score": float(row["score"] or 0.0),
            "trigger_count": int(row["trigger_count"] or 1),
            "detector_flatness": float(row["spectral_flatness"] or 0.0),
            "tonal_penalty": float(row["tonal_penalty"] or 0.0),
            "context_start": round(start, 3),
            "context_end": round(end, 3),
            "before_frame_sec": round(before_t, 3),
            "peak_frame_sec": round(peak_t, 3),
            "after_frame_sec": round(after_t, 3),
            **features,
            "before_image": before.name,
            "peak_image": middle.name,
            "after_image": after.name,
            "spectrogram": spec.name,
        }
        records.append(record)
        print(f"[{sample_no}/{len(selected)}] {row['review_tier']} candidate {row['id']} peak={peak:.3f}s")

    manifest = out_dir / "audit_static_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)

    font = default_font(18)
    small = default_font(15)
    sheet_paths = []

    for sheet_index in range(math.ceil(len(records) / ROWS_PER_SHEET)):
        chunk = records[sheet_index * ROWS_PER_SHEET:(sheet_index + 1) * ROWS_PER_SHEET]
        canvas = Image.new("RGB", (SPEC_W, ROW_H * len(chunk)), "black")
        draw = ImageDraw.Draw(canvas)

        for row_index, rec in enumerate(chunk):
            y0 = row_index * ROW_H
            label = (
                f"S{rec['sample_no']:02d} C{rec['candidate_id']} {rec['review_tier']} "
                f"peak={rec['candidate_peak']:.3f}s score={rec['score']:.2f} "
                f"review={rec['review_score']:.2f} trig={rec['trigger_count']} "
                f"flat={rec['detector_flatness']:.3f}"
            )
            draw.rectangle((0, y0, SPEC_W, y0 + LABEL_H), fill=(20, 20, 20))
            draw.text((10, y0 + 8), label, font=font, fill="white")

            frames = [rec["before_image"], rec["peak_image"], rec["after_image"]]
            captions = ["-0.75 s", "PEAK", "+0.75 s"]
            for j, (name, caption) in enumerate(zip(frames, captions)):
                img = Image.open(out_dir / name).convert("RGB")
                canvas.paste(img, (j * FRAME_W, y0 + LABEL_H))
                d2 = ImageDraw.Draw(canvas)
                d2.rectangle((j * FRAME_W + 5, y0 + LABEL_H + 5,
                              j * FRAME_W + 95, y0 + LABEL_H + 27), fill=(0, 0, 0))
                d2.text((j * FRAME_W + 10, y0 + LABEL_H + 7), caption, font=small, fill="white")

            spec = Image.open(out_dir / rec["spectrogram"]).convert("RGB")
            spec_y = y0 + LABEL_H + FRAME_H
            canvas.paste(spec, (0, spec_y))

            rel = (rec["candidate_peak"] - rec["context_start"]) / max(1e-9, (rec["context_end"] - rec["context_start"]))
            x = int(np.clip(rel, 0.0, 1.0) * (SPEC_W - 1))
            d3 = ImageDraw.Draw(canvas)
            d3.line((x, spec_y, x, spec_y + SPEC_H - 1), fill="white", width=2)

        sheet = EXPORTS / f"audit_static_video_{args.video_id:04d}_sheet_{sheet_index + 1:02d}.png"
        canvas.save(sheet, optimize=True)
        sheet_paths.append(sheet)

    export_manifest = EXPORTS / f"audit_static_video_{args.video_id:04d}_manifest.csv"
    shutil.copy2(manifest, export_manifest)

    readme = EXPORTS / f"audit_static_video_{args.video_id:04d}_README.txt"
    readme.write_text(
        "Static detector audit packet\n"
        f"Video ID: {args.video_id}\n"
        f"Audit scope: {audit_scope}\n"
        f"Samples: {len(records)} / {len(rows)} eligible candidates\n"
        f"Context: {args.context:.2f} s around candidate peak\n"
        "Each row: frame before / peak / after, then a 3-second spectrogram.\n"
        "The white vertical line in the spectrogram marks the detector peak.\n",
        encoding="utf-8",
    )

    print()
    print("STATIC AUDIT PACKET CREATED")
    print(f"Audit scope: {audit_scope}")
    print(f"Manifest: {export_manifest}")
    for p in sheet_paths:
        print(f"Sheet   : {p}")
    print(f"README  : {readme}")
    print("Upload the PNG sheets and manifest for Detector V0.2 audit.")


if __name__ == "__main__":
    main()
