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


def union_duration(intervals):
    if not intervals:
        return 0.0
    spans = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not spans:
        return 0.0
    total = 0.0
    cur_a, cur_b = spans[0]
    for a, b in spans[1:]:
        if a <= cur_b:
            cur_b = max(cur_b, b)
        else:
            total += cur_b - cur_a
            cur_a, cur_b = a, b
    total += cur_b - cur_a
    return total


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
    summed = sum(lengths)
    union = union_duration([(r["start_sec"], r["end_sec"]) for r in rows])
    overlap = max(0.0, summed - union)
    rate_min = count / duration * 60.0 if duration > 0 else 0.0

    print("SFX 532 Candidate Report")
    print("=" * 60)
    print(f"Video ID                : {args.video_id}")
    print(f"File                    : {video['filename']}")
    print(f"Duration                : {duration:.3f} s")
    print(f"Candidates              : {count}")
    print(f"Candidates / minute     : {rate_min:.2f}")
    print(f"Duration sum            : {summed:.3f} s  (counts overlap more than once)")
    print(f"Union coverage          : {union:.3f} s")
    print(f"Union coverage ratio    : {(union/duration*100.0 if duration else 0):.1f}%")
    print(f"Overlapped duration sum : {overlap:.3f} s")
    print()
    print("Candidate length (s)")
    print(f"  min / median / max    : {min(lengths):.3f} / {statistics.median(lengths):.3f} / {max(lengths):.3f}")
    print(f"  P10 / P25 / P75 / P90: {percentile(lengths,10):.3f} / {percentile(lengths,25):.3f} / {percentile(lengths,75):.3f} / {percentile(lengths,90):.3f}")
    print()
    print("Detector score")
    print(f"  min / median / max    : {min(scores):.3f} / {statistics.median(scores):.3f} / {max(scores):.3f}")
    print(f"  P10 / P25 / P75 / P90 / P95: {percentile(scores,10):.3f} / {percentile(scores,25):.3f} / {percentile(scores,75):.3f} / {percentile(scores,90):.3f} / {percentile(scores,95):.3f}")
    print()
    print("Important: candidate count/coverage alone cannot decide true SFX precision.")
    print("Use an audit reel with visual context before tuning detector thresholds.")


if __name__ == "__main__":
    main()
