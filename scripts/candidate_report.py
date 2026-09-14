from pathlib import Path
import argparse
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import connect


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", type=int, required=True)
    args = ap.parse_args()

    with connect() as con:
        video = con.execute("SELECT * FROM videos WHERE id=?", (args.video_id,)).fetchone()
        if not video:
            raise SystemExit(f"Unknown video_id={args.video_id}")
        rows = con.execute(
            "SELECT * FROM event_candidates WHERE video_id=? ORDER BY start_sec",
            (args.video_id,),
        ).fetchall()

    duration = float(video["duration_sec"] or 0.0)
    count = len(rows)
    if count == 0:
        print("No candidates found.")
        return

    lengths = [float(r["end_sec"] - r["start_sec"]) for r in rows]
    scores = [float(r["score"] or 0.0) for r in rows]
    covered = sum(lengths)
    rate_min = count / duration * 60.0 if duration > 0 else 0.0

    print("SFX 532 Candidate Report")
    print("=" * 60)
    print(f"Video ID              : {args.video_id}")
    print(f"File                  : {video['filename']}")
    print(f"Duration              : {duration:.3f} s")
    print(f"Candidates            : {count}")
    print(f"Candidates / minute   : {rate_min:.2f}")
    print(f"Candidate duration sum: {covered:.3f} s")
    print(f"Raw coverage ratio    : {(covered/duration*100.0 if duration else 0):.1f}%")
    print()
    print("Candidate length (s)")
    print(f"  min / median / max  : {min(lengths):.3f} / {statistics.median(lengths):.3f} / {max(lengths):.3f}")
    print(f"  P10 / P25 / P75 / P90: {percentile(lengths,10):.3f} / {percentile(lengths,25):.3f} / {percentile(lengths,75):.3f} / {percentile(lengths,90):.3f}")
    print()
    print("Detector score")
    print(f"  min / median / max  : {min(scores):.3f} / {statistics.median(scores):.3f} / {max(scores):.3f}")
    print(f"  P10 / P25 / P75 / P90 / P95: {percentile(scores,10):.3f} / {percentile(scores,25):.3f} / {percentile(scores,75):.3f} / {percentile(scores,90):.3f} / {percentile(scores,95):.3f}")
    print()
    print("Important: this report does NOT decide which candidates are true SFX.")
    print("Use the audit sample next to measure precision/recall before tuning thresholds.")


if __name__ == "__main__":
    main()
