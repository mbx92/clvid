import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from app.config import get_settings
from app.domain.models import Asset
from app.storage.local import LocalStorage
from app.story.schemas import Document
from app.story.media import normalize_upload, render_story

pytestmark = pytest.mark.skipif(not Path('/opt/remotion/story-render.mjs').is_file(), reason='Built Remotion worker required')

def cmd(*args):
    return subprocess.run(['ffmpeg','-v','error','-y',*args],check=True,capture_output=True).stdout

@pytest.mark.parametrize('aspect', ['portrait','landscape','square'])
def test_real_story_render_with_image_video_and_voice(monkeypatch, tmp_path, aspect):
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path / 'media')
    monkeypatch.setattr(settings, 'min_free_disk_bytes', 0)
    storage = LocalStorage()
    image = storage.prepare('samples/image.png')
    cmd('-f','lavfi','-i','color=c=red:s=320x240','-frames:v','1',str(image))
    video = storage.prepare('samples/video.mp4')
    cmd('-f','lavfi','-i','color=c=blue:s=320x240:r=30','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(video))
    audio = storage.prepare('samples/audio.wav')
    cmd('-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1',str(audio))
    normalized,mime,meta = normalize_upload(audio,'.wav',settings)
    assets = [Asset(id='image',storage_key='samples/image.png',mime='image/png',meta_json={'story_kind':'image'}),
              Asset(id='video',storage_key='samples/video.mp4',mime='video/mp4',meta_json={'story_kind':'video'}),
              Asset(id='audio',storage_key='samples/audio.m4a',mime=mime,meta_json=meta)]
    assert normalized == storage.path('samples/audio.m4a')
    d = Document(title='Render test',aspect=aspect,scenes=[
        {'id':'one','title':'Cerita pertama','layout':'split','duration_ms':1000,'asset_id':'image','audio_id':'audio','narration':'Suara pertama.'},
        {'id':'two','title':'Cerita kedua','layout':'quote','duration_ms':1000,'asset_id':'video','narration':'Adegan kedua.'}]).model_dump()
    directory = tmp_path / 'render'; directory.mkdir()
    ctx = SimpleNamespace(stage=lambda *_:None,cancelled=lambda:False,progress=lambda *_:None)
    output,srt,meta = render_story(d, assets, directory, settings, ctx)
    assert abs(meta['duration_ms']-2000) < 150
    assert meta['video_codec'] == 'h264' and meta['audio_codec'] == 'aac'
    assert 'Suara pertama.' in srt.read_text() and 'Adegan kedua.' in srt.read_text()
    pixels = cmd('-ss','0.5','-i',str(output),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-')
    assert sum(pixels) > 30
    sound = cmd('-i',str(output),'-t','0.8','-vn','-ac','1','-ar','8000','-f','s16le','-')
    assert any(sound)

def test_text_only_story_has_silent_audio_and_matching_subtitle_chunks(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path / 'media')
    monkeypatch.setattr(settings, 'min_free_disk_bytes', 0)
    narration = 'Ini adalah cerita yang cukup panjang untuk dibagi menjadi beberapa bagian subtitle pada satu adegan.'
    d = Document(title='Tanpa aset', scenes=[{'id':'one','title':'Cerita Anda','duration_ms':1000,'narration':narration}]).model_dump()
    directory = tmp_path / 'render'; directory.mkdir()
    ctx = SimpleNamespace(stage=lambda *_:None,cancelled=lambda:False,progress=lambda *_:None)
    output,srt,meta = render_story(d, [], directory, settings, ctx)
    assert meta['audio_codec'] == 'aac' and abs(meta['duration_ms']-1000) < 150
    assert srt.read_text().count('-->') == 2
    assert '00:00:00,500' in srt.read_text()
    sound = cmd('-i',str(output),'-vn','-ac','1','-ar','8000','-f','s16le','-')
    assert not any(sound)


def test_real_coffee_illustrations_export_without_media_and_reveal_answer(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path / 'media')
    monkeypatch.setattr(settings, 'min_free_disk_bytes', 0)
    kinds = ['coffee_compare','coffee_flat','coffee_pair','coffee_separate','coffee_peaberry','coffee_reveal']
    d = Document(title='Kopi',scenes=[{'id':k,'title':'Biji kopi','duration_ms':1000,'visual':{'kind':k,'motion':'still','reveal_ms':500}} for k in kinds]).model_dump()
    directory = tmp_path / 'render'; directory.mkdir()
    ctx = SimpleNamespace(stage=lambda *_:None,cancelled=lambda:False,progress=lambda *_:None)
    output,_,meta = render_story(d, [], directory, settings, ctx)
    assert abs(meta['duration_ms'] - 6000) < 150 and meta['video_codec'] == 'h264'
    # The same title/theme on each scene isolates differences to the illustrations.
    def pixels(seconds):
        return cmd('-ss',str(seconds),'-i',str(output),'-frames:v','1','-vf','crop=600:420:60:220,scale=32:32','-pix_fmt','rgb24','-f','rawvideo','-')
    frames = [pixels(i+.8) for i in range(6)]
    assert len(set(frames)) == 6
    assert pixels(5.2) != pixels(5.8)
    assert all(sum(frame)/len(frame) > 90 for frame in frames)


def test_real_story_timed_caption_pauses_match_exported_srt(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, 'media_root', tmp_path / 'media')
    monkeypatch.setattr(settings, 'min_free_disk_bytes', 0)
    audio = LocalStorage().prepare('samples/timed.m4a')
    cmd('-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', '3', '-c:a', 'aac', str(audio))
    asset = Asset(id='voice', storage_key='samples/timed.m4a', mime='audio/mp4', meta_json={'story_kind': 'audio'})
    narration = 'Awal. Akhir.'
    d = Document(scenes=[{'id': 'one', 'title': '', 'duration_ms': 3000, 'narration': narration,
        'audio_id': 'voice', 'caption_audio_id': 'voice', 'caption_narration': narration,
        'captions': [{'start_ms': 300, 'end_ms': 800, 'text': 'Awal.'},
                     {'start_ms': 2200, 'end_ms': 2800, 'text': 'Akhir.'}]}]).model_dump()
    directory = tmp_path / 'render'; directory.mkdir()
    ctx = SimpleNamespace(stage=lambda *_: None, cancelled=lambda: False, progress=lambda *_: None)
    output, srt, _ = render_story(d, [asset], directory, settings, ctx)
    assert '00:00:00,300 --> 00:00:00,800' in srt.read_text()
    assert '00:00:02,200 --> 00:00:02,800' in srt.read_text()
    # This crop contains only the caption area, excluding the animated progress bar.
    def pixels(seconds):
        return cmd('-ss', str(seconds), '-i', str(output), '-frames:v', '1', '-vf',
                   'crop=600:80:60:1160,scale=150:20', '-pix_fmt', 'gray', '-f', 'rawvideo', '-')
    blank, first, pause, last = [pixels(t) for t in (.1, .5, 1.5, 2.5)]
    assert first != blank and last != pause
    # H.264 can vary a few pixels between blank frames; caption text raises luma substantially.
    assert max(blank) < 60 and max(pause) < 60
    assert max(first) > 150 and max(last) > 150
