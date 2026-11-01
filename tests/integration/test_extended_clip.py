"""Real processing paths beyond the former three-minute ceiling."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from app.media.render import render_clip, reusable_tracking_result
from app.media.speaker_model import score_speakers
from app.media.tracking_versions import FACE_METHOD

FFMPEG = os.environ.get('FFMPEG_PATH', 'ffmpeg')
FFPROBE = os.environ.get('FFPROBE_PATH', 'ffprobe')
pytestmark = pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which(FFPROBE), reason='FFmpeg required')


def test_long_clip_render_and_speaker_input_accept_extended_duration(tmp_path):
    source, audio = tmp_path/'long.mp4', tmp_path/'long.wav'
    subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=blue:s=64x64:r=25',
                    '-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t','181','-c:v','libx264','-preset','ultrafast',
                    '-c:a','aac',str(source)], check=True)
    subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(source),'-vn','-ac','1','-ar','16000',
                    '-c:a','pcm_s16le',str(audio)], check=True)
    model = tmp_path/'unused.onnx'
    model.touch()
    # No visible tracks: an honest negative result, not a short-duration rejection.
    assert score_speakers(source, audio, [], model) == {}
    result = render_clip(source, tmp_path/'render', {'start_ms':0, 'end_ms':181000,
                         'crop_json':{'mode':'fit'},'subtitle_style_json':{'enabled':False}}, {'width':720},
                         ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert abs(result['meta']['duration_ms'] - 181000) <= 100
    assert result['meta']['width'] == 720
    framing = {'mode':'face','method':FACE_METHOD,'total_frames':3600,'detected_frames':3600,
               'fallback_reason':None,'keyframes':[{'t_ms':t,'x':.5,'y':.5} for t in range(0,600001,200)]}
    assert reusable_tracking_result(framing, {'mode':'fill','tracking':'face'}, 600000)
