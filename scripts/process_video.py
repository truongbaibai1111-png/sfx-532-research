from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfx532.pipeline import process_video

parser = argparse.ArgumentParser(description="Process one video only")
parser.add_argument("--video-id", type=int, required=True)
parser.add_argument(
    "--detect-only",
    action="store_true",
    help="Run detection + SQLite update without generating WAV/MP4/frame packages",
)
args = parser.parse_args()

result = process_video(args.video_id, package_artifacts=not args.detect_only)
print(result)
