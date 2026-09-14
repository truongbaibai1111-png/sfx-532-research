from pathlib import Path
import argparse
import csv
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import connect
from sfx532.paths import EVENTS, EXPORTS, RAW


def pick_indices(n, count):
    if n <= count:
        return list(range(n))
    # Stratified across the full timeline so the sample does not only contain
    # high-score transients from one part of the video.
    out = []
    for i in range(count):
        idx = round(i * (n - 1) / (count - 1)) if count > 1 else 0
        if idx not in out:
            out.append(idx)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", type=int, required=True)
    ap.add_argument("--count", type=int, default=24)
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

    indices = pick_indices(len(rows), min(args.count, len(rows)))
    selected = [rows[i] for i in indices]

    out_dir = EXPORTS / f"audit_video_{args.video_id:04d}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = out_dir / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([
            "candidate_id", "start_sec", "end_sec", "peak_sec", "score",
            "video_clip", "audio_clip", "frame_before", "frame_peak", "frame_after"
        ])
        for r in selected:
            copied = {}
            for key in [
                "video_clip_relpath", "audio_clip_relpath", "frame_before_relpath",
                "frame_peak_relpath", "frame_after_relpath"
            ]:
                rel = r[key]
                if not rel:
                    copied[key] = ""
                    continue
                src = RAW.parent / rel
                if not src.exists():
                    copied[key] = ""
                    continue
                dst = out_dir / f"cand_{r['id']:04d}_{src.name}"
                shutil.copy2(src, dst)
                copied[key] = dst.name

            w.writerow([
                r["id"], r["start_sec"], r["end_sec"], r["peak_sec"], r["score"],
                copied.get("video_clip_relpath", ""),
                copied.get("audio_clip_relpath", ""),
                copied.get("frame_before_relpath", ""),
                copied.get("frame_peak_relpath", ""),
                copied.get("frame_after_relpath", ""),
            ])

    readme = out_dir / "README.txt"
    readme.write_text(
        "SFX 532 audit sample\n"
        f"Video ID: {args.video_id}\n"
        f"Source file: {video['filename']}\n"
        f"Total candidates: {len(rows)}\n"
        f"Sampled candidates: {len(selected)}\n\n"
        "The sample is stratified over the whole timeline. It is for manual detector audit,\n"
        "not for final SFX labeling. Review each MP4 together with the WAV and frames.\n",
        encoding="utf-8",
    )

    zip_path = EXPORTS / f"audit_video_{args.video_id:04d}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in out_dir.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(out_dir))

    print(f"Audit sample created: {zip_path}")
    print(f"Candidates sampled   : {len(selected)} / {len(rows)}")
    print("Upload this ZIP for detector review before changing thresholds.")


if __name__ == "__main__":
    main()
