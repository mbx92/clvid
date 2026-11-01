"""Generate a distributable synthetic AV fixture; requires FFmpeg with libx264."""
import argparse
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path(".artifacts/fixture-source.mp4"))
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([
    os.environ.get("FFMPEG_PATH", "ffmpeg"), "-hide_banner", "-loglevel", "error",
    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=12",
    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=12",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
    "-movflags", "+faststart", "-y", str(args.output),
], check=True, timeout=120)
print(args.output.resolve())
