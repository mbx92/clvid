"""Exercise the real yt-dlp merger under the import subprocess guard."""
import json
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_ytdlp_merges_separate_streams_with_local_protocol_whitelist(tmp_path):
    video, audio, output = [tmp_path/name for name in ("video.mp4", "audio.m4a", "source.mp4")]
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run([*common, "-f", "lavfi", "-i", "color=blue:s=160x90:r=25", "-t", "1", "-an", "-c:v", "libx264", str(video)], check=True)
    subprocess.run([*common, "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1", "-c:a", "aac", str(audio)], check=True)
    script = '''
from pathlib import Path
import shutil,sys
from yt_dlp import YoutubeDL
from yt_dlp.postprocessor.ffmpeg import FFmpegMergerPP
from app.media.import_child import install_process_guard, local_postprocessor_args
directory = Path(sys.argv[1])
install_process_guard(directory)
with YoutubeDL({'quiet':True, 'ffmpeg_location':shutil.which('ffmpeg'),
                'postprocessor_args':local_postprocessor_args()}) as downloader:
    FFmpegMergerPP(downloader).run({'filepath':str(directory/'source.mp4'), 'ext':'mp4',
        '__files_to_merge':[str(directory/'video.mp4'),str(directory/'audio.m4a')],
        'requested_formats':[{'vcodec':'h264','acodec':'none','protocol':'https'},
                             {'vcodec':'none','acodec':'aac','protocol':'https'}]})
'''
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)], capture_output=True, text=True, check=True)
    assert [s["codec_name"] for s in json.loads(probe.stdout)["streams"]] == ["h264", "aac"]
