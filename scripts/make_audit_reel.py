from pathlib import Path
import argparse
import csv
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import connect
from sfx532.paths import EXPORTS, RAW


def pick_indices(n, count):
    if n <= count:
        return list(range(n))
    return [round(i * (n - 1) / (count - 1)) for i in range(count)] if count > 1 else [0]


def run(cmd):
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", type=int, required=True)
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--context", type=float, default=3.0,
                    help="Seconds of visual/audio context per sampled candidate")
    args = ap.parse_args()

    with connect() as con:
        video = con.execute("SELECT * FROM videos WHERE id=?", (args.video_id,)).fetchone()
        if not video:
            raise SystemExit(f"Unknown video_id={args.video_id}")
        rows = con.execute(
            "SELECT * FROM event_candidates WHERE video_id=? ORDER BY start_sec",
            (args.video_id,),
        ).fetchall()

    if not rows:
        raise SystemExit("No candidates. Run process_video.py first.")

    source = RAW / video["relpath"]
    if not source.exists():
        raise SystemExit(f"Raw video not found: {source}")

    indices = pick_indices(len(rows), min(args.count, len(rows)))
    selected = [rows[i] for i in indices]

    out_dir = EXPORTS / f"audit_reel_video_{args.video_id:04d}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_duration = float(video["duration_sec"] or 0.0)
    half = args.context / 2.0
    manifest_path = out_dir / "manifest.csv"
    concat_path = out_dir / "concat.txt"
    concat_lines = []

    with manifest_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([
            "sample_no", "candidate_id", "candidate_start", "candidate_end",
            "candidate_peak", "score", "context_start", "context_end", "reel_start_sec"
        ])

        reel_cursor = 0.0
        for sample_no, row in enumerate(selected, start=1):
            peak = float(row["peak_sec"] or row["start_sec"])
            start = max(0.0, peak - half)
            end = min(source_duration, start + args.context)
            if end - start < args.context and end >= source_duration:
                start = max(0.0, end - args.context)
            duration = max(0.2, end - start)

            clip = out_dir / f"{sample_no:02d}_cand_{row['id']:04d}_t_{peak:07.3f}.mp4"
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                "-err_detect", "ignore_err",
                "-fflags", "+genpts",
                "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
                "-map", "0:v:0", "-map", "0:a?",
                "-vf", "scale=960:-2:flags=lanczos,fps=30,format=yuv420p,setpts=PTS-STARTPTS",
                "-af", "aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                "-movflags", "+faststart", str(clip),
            ]
            run(cmd)

            concat_lines.append(f"file '{clip.name}'")
            w.writerow([
                sample_no, row["id"], row["start_sec"], row["end_sec"],
                row["peak_sec"], row["score"], round(start, 3), round(end, 3),
                round(reel_cursor, 3),
            ])
            reel_cursor += duration
            print(f"[{sample_no}/{len(selected)}] candidate {row['id']} peak={peak:.3f}s")

    concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    reel_path = EXPORTS / f"audit_reel_video_{args.video_id:04d}.mp4"
    if reel_path.exists():
        reel_path.unlink()

    # Re-encode the final reel instead of stream-copying clip timestamps.
    # This intentionally costs a little more CPU but produces a clean monotonic
    # timeline, which matters for visual/audio detector auditing.
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-fflags", "+genpts",
        "-f", "concat", "-safe", "0", "-i", str(concat_path),
        "-vf", "fps=30,format=yuv420p,setpts=PTS-STARTPTS",
        "-af", "aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart", str(reel_path),
    ])

    export_manifest = EXPORTS / f"audit_reel_video_{args.video_id:04d}_manifest.csv"
    shutil.copy2(manifest_path, export_manifest)

    print()
    print(f"Audit reel created : {reel_path}")
    print(f"Manifest           : {export_manifest}")
    print(f"Samples            : {len(selected)} / {len(rows)}")
    print(f"Context per sample : {args.context:.2f} s")
    print("Final reel timestamps were regenerated by re-encoding.")
    print("Upload the MP4 and manifest for visual+audio detector audit.")


if __name__ == "__main__":
    main()
