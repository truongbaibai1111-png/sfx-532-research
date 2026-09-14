from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.db import init_db, connect

init_db()

with connect() as con:
    rows = con.execute(
        """
        SELECT v.id, v.filename, v.duration_sec, v.has_audio, v.process_status,
               COUNT(c.id) AS candidates,
               SUM(CASE WHEN c.review_tier='PRIMARY' THEN 1 ELSE 0 END) AS primary_count,
               SUM(CASE WHEN c.review_tier='SECONDARY' THEN 1 ELSE 0 END) AS secondary_count
        FROM videos v
        LEFT JOIN event_candidates c ON c.video_id=v.id
        GROUP BY v.id
        ORDER BY v.id
        """
    ).fetchall()

if not rows:
    print("Database has no videos. Run: python scripts/scan_videos.py")
else:
    print(f"{'ID':>4}  {'STATUS':<18} {'AUDIO':<5} {'ALL':>5} {'PRI':>5} {'SEC':>5} {'DURATION':>9}  FILE")
    print("-" * 112)
    for row in rows:
        duration = f"{row['duration_sec']:.1f}s" if row['duration_sec'] is not None else "?"
        print(
            f"{row['id']:>4}  {row['process_status']:<18} "
            f"{('yes' if row['has_audio'] else 'no'):<5} "
            f"{int(row['candidates'] or 0):>5} "
            f"{int(row['primary_count'] or 0):>5} "
            f"{int(row['secondary_count'] or 0):>5} "
            f"{duration:>9}  {row['filename']}"
        )
