from pathlib import Path
import argparse
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import connect, init_db


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


def _summary(rows, duration):
    if not rows:
        return None
    lengths = [float(r["end_sec"] - r["start_sec"]) for r in rows]
    scores = [float(r["score"] or 0.0) for r in rows]
    review_scores = [float(r["review_score"] or 0.0) for r in rows]
    summed = sum(lengths)
    union = union_duration([(r["start_sec"], r["end_sec"]) for r in rows])
    return {
        "count": len(rows),
        "rate": len(rows) / duration * 60.0 if duration > 0 else 0.0,
        "summed": summed,
        "union": union,
        "overlap": max(0.0, summed - union),
        "lengths": lengths,
        "scores": scores,
        "review_scores": review_scores,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", type=int, required=True)
    args = ap.parse_args()

    init_db()
    with connect() as con:
        video = con.execute("SELECT * FROM videos WHERE id=?", (args.video_id,)).fetchone()
        if not video:
            raise SystemExit(f"Unknown video_id={args.video_id}")
        rows = con.execute(
            "SELECT * FROM event_candidates WHERE video_id=? ORDER BY start_sec",
            (args.video_id,),
        ).fetchall()

    duration = float(video["duration_sec"] or 0.0)
    if not rows:
        print("No candidates found.")
        return

    primary = [r for r in rows if (r["review_tier"] or "PRIMARY") == "PRIMARY"]
    secondary = [r for r in rows if (r["review_tier"] or "PRIMARY") != "PRIMARY"]

    all_stats = _summary(rows, duration)
    primary_stats = _summary(primary, duration)

    print("SFX 532 Candidate Report — Detector V0.2")
    print("=" * 64)
    print(f"Video ID                  : {args.video_id}")
    print(f"File                      : {video['filename']}")
    print(f"Duration                  : {duration:.3f} s")
    print(f"All retained candidates   : {len(rows)}")
    print(f"PRIMARY review candidates : {len(primary)}")
    print(f"SECONDARY metadata only   : {len(secondary)}")
    print(f"PRIMARY / minute          : {(len(primary)/duration*60.0 if duration else 0):.2f}")
    print()

    print("All retained candidates")
    print(f"  Duration sum            : {all_stats['summed']:.3f} s")
    print(f"  Union coverage          : {all_stats['union']:.3f} s")
    print(f"  Union coverage ratio    : {(all_stats['union']/duration*100.0 if duration else 0):.1f}%")
    print(f"  Overlapped duration sum : {all_stats['overlap']:.3f} s")
    print()

    if primary_stats:
        lengths = primary_stats["lengths"]
        scores = primary_stats["scores"]
        review_scores = primary_stats["review_scores"]
        print("PRIMARY candidate length (s)")
        print(f"  min / median / max      : {min(lengths):.3f} / {statistics.median(lengths):.3f} / {max(lengths):.3f}")
        print(f"  P10 / P25 / P75 / P90  : {percentile(lengths,10):.3f} / {percentile(lengths,25):.3f} / {percentile(lengths,75):.3f} / {percentile(lengths,90):.3f}")
        print()
        print("PRIMARY detector score")
        print(f"  min / median / max      : {min(scores):.3f} / {statistics.median(scores):.3f} / {max(scores):.3f}")
        print(f"  review score median     : {statistics.median(review_scores):.3f}")
        print(f"  review P10 / P90        : {percentile(review_scores,10):.3f} / {percentile(review_scores,90):.3f}")
        print()
        print(f"PRIMARY union coverage    : {primary_stats['union']:.3f} s")
        print(f"PRIMARY coverage ratio    : {(primary_stats['union']/duration*100.0 if duration else 0):.1f}%")

    clustered = sum(1 for r in rows if int(r["trigger_count"] or 1) > 1)
    tonal = sum(1 for r in rows if float(r["tonal_penalty"] or 0.0) > 0)
    print()
    print(f"Candidates merged from multiple triggers : {clustered}")
    print(f"Candidates receiving tonal down-rank      : {tonal}")
    print()
    print("PRIMARY = generate WAV/MP4/frames and review first.")
    print("SECONDARY = timestamp/features stay in SQLite; not discarded.")
    print("Do not compare only total count with V0.1; compare PRIMARY precision and recall.")


if __name__ == "__main__":
    main()
