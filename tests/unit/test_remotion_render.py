"""Remotion adapter contract without a browser or external video dependencies."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.media import remotion, render
from app.media.process import Cancelled, MediaError, ProcessResult


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    script = tmp_path / "render.mjs"
    script.write_text("// test-only CLI placeholder", encoding="utf-8")
    captured = {}
    snapshot = dict(start_ms=1000, end_ms=7000, crop_json={"mode": "gaming"},
                    subtitle_style_json={"renderer": "remotion", "remotion_template": "cinematic", "enabled": True, "display_mode": "words"},
                    cues=[dict(start_ms=0, end_ms=5000, text="Kalimat asli")],
                    subtitle_events=[dict(start_ms=100, end_ms=600, text="Kalimat")])
    framing = {"mode": "static", "method": "gaming-layout-1", "analysis_reused": False}
    meta = dict(width=720, height=1280, duration_ms=6000, fps=30, video_codec="h264",
                pixel_format="yuv420p", audio_codec="aac", sample_aspect_ratio=1, rotation=0)

    def prepare(source, directory, saved_snapshot, config, **options):
        captured["prepare"] = (deepcopy(saved_snapshot), options)
        directory.mkdir(parents=True)
        mp4, srt = directory / "clip.mp4", directory / "captions.srt"
        mp4.write_bytes(b"prepared-video-with-audio")
        srt.write_text("\n".join(cue["text"] for cue in saved_snapshot["cues"]), encoding="utf-8")
        return dict(mp4=mp4, srt=srt, meta={**meta, "framing": framing})

    def run(args, **options):
        manifest = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
        captured["node"] = (args, options, manifest)
        Path(manifest["outputPath"]).write_bytes(b"muted-remotion-video")
        return ProcessResult("segment_end_ms=6000\n", "", 0)

    def mux(args, **options):
        captured["mux"] = (args, options)
        Path(args[-1]).write_bytes(b"final-video")

    monkeypatch.setattr(remotion, "run_process", run)
    monkeypatch.setattr(remotion, "ffmpeg", mux)
    monkeypatch.setattr(remotion, "probe", lambda *args, **options: dict(meta))
    return dict(script=script, directory=tmp_path / "output", snapshot=snapshot, meta=meta,
                prepare=prepare, captured=captured, framing=framing,
                config={"width": 720, "renderer": "remotion", "renderer_version": remotion.REMOTION_RENDERER_VERSION})


def invoke(adapter, **options):
    return remotion.render_remotion("source.mp4", adapter["directory"], adapter["snapshot"], adapter["config"],
                                    prepare=adapter["prepare"], script_path=adapter["script"], **options)


def test_manifest_keeps_word_events_style_and_framing_while_muxing_audio_only_once(adapter):
    unchanged = deepcopy(adapter["snapshot"])
    cancelled, progress = lambda: False, lambda value: None
    stages = []
    result = invoke(adapter, node_path="custom-node", cancelled=cancelled, progress=progress,
                    timeout=123, stage=stages.append, tracking_result={"cached": True})
    captured = adapter["captured"]
    saved, preparation = captured["prepare"]
    assert saved["subtitle_style_json"]["enabled"] is False
    assert preparation["tracking_result"] == {"cached": True}
    assert adapter["snapshot"] == unchanged
    args, options, manifest = captured["node"]
    assert args[0] == "custom-node" and args[1] == str(adapter["script"].resolve())
    assert options == dict(timeout=123, cancelled=cancelled, progress=progress, duration_ms=6000)
    assert manifest == dict(version=1, durationMs=6000, width=720, height=1280, fps=30,
                            videoPath=str((adapter["directory"] / "prepared/clip.mp4").resolve()),
                            outputPath=str((adapter["directory"] / "remotion.partial.mp4").resolve()),
                            cues=unchanged["subtitle_events"], style=unchanged["subtitle_style_json"])
    mux, mux_options = captured["mux"]
    assert [mux[i + 1] for i, item in enumerate(mux) if item == "-map"] == ["0:v:0", "1:a:0"]
    assert mux[mux.index("-c") + 1] == "copy" and "-c:a" not in mux
    assert mux_options["cancelled"] is cancelled and mux_options["timeout"] == 123
    assert result["mp4"].is_file() and result["srt"].read_text() == "Kalimat asli"
    assert result["meta"]["framing"] == adapter["framing"]
    assert result["meta"]["renderer_version"] == remotion.REMOTION_RENDERER_VERSION
    assert result["meta"]["remotion_template"] == "cinematic"
    assert stages == ["render_remotion", "finalize_render"]
    assert not Path(manifest["videoPath"]).exists() and not Path(manifest["outputPath"]).exists()


def test_disabled_subtitles_remain_disabled_and_srt_is_preserved(adapter):
    adapter["snapshot"]["subtitle_style_json"]["enabled"] = False
    result = invoke(adapter)
    assert adapter["captured"]["node"][2]["style"]["enabled"] is False
    assert adapter["captured"]["node"][2]["cues"] == []
    assert result["srt"].read_text() == "Kalimat asli"


def test_podcast_manifest_keeps_whole_sentence_and_word_timing(adapter):
    adapter['snapshot']['subtitle_style_json'].update(remotion_template='podcast', display_mode='sentence')
    events = [{'start_ms': 0, 'end_ms': 5000, 'text': 'Kalimat asli', 'word_spans': [
        {'start_ms': 100, 'end_ms': 600, 'start_word': 0, 'end_word': 1},
        {'start_ms': 800, 'end_ms': 1200, 'start_word': 1, 'end_word': 2}]}]
    adapter['snapshot']['subtitle_events'] = events
    result = invoke(adapter)
    assert adapter['captured']['node'][2]['cues'] == events
    assert result['srt'].read_text() == 'Kalimat asli'


def test_video_effects_survive_disabled_captions_without_changing_source_or_audio_duration(adapter):
    effects = {
        "transition_in": "fade", "transition_out": "slide", "transition_ms": 300,
        "intro": {"enabled": True, "text": "PERTARUNGAN DIMULAI", "duration_ms": 1200},
        "outro": {"enabled": True, "text": "LANJUT BAGIAN BERIKUTNYA", "duration_ms": 1500},
        "zooms": [{"start_ms": 1000, "end_ms": 3000, "scale": 1.4, "x": .3, "y": .6}],
    }
    adapter["snapshot"]["subtitle_style_json"].update(enabled=False, remotion_effects=effects)
    unchanged = deepcopy(adapter["snapshot"])
    result = invoke(adapter)
    manifest = adapter["captured"]["node"][2]
    assert manifest["cues"] == [] and manifest["style"]["remotion_effects"] == effects
    assert manifest["durationMs"] == 6000 and adapter["snapshot"] == unchanged
    mux = adapter["captured"]["mux"][0]
    assert mux[mux.index("-t") + 1] == "6.0"
    assert result["meta"]["duration_ms"] == 6000 and result["srt"].read_text() == "Kalimat asli"


def test_large_disabled_captions_do_not_enter_visual_manifest_but_reach_srt_preparation(adapter):
    adapter["snapshot"]["subtitle_style_json"]["enabled"] = False
    old_text = "PRIVATE_DISABLED_SUBTITLE_" * 100000
    old_cues = [{"start_ms": 0, "end_ms": 6000, "text": old_text}]
    adapter["snapshot"]["cues"] = old_cues
    adapter["snapshot"]["subtitle_events"] = old_cues
    result = invoke(adapter)
    assert adapter["captured"]["prepare"][0]["cues"] == old_cues
    assert adapter["captured"]["node"][2]["cues"] == []
    serialized = (adapter["directory"] / "remotion.json").read_text(encoding="utf-8")
    assert len(serialized) < 2000 and "PRIVATE_DISABLED_SUBTITLE_" not in serialized
    assert result["srt"].read_text(encoding="utf-8") == old_text
    assert adapter["snapshot"]["cues"] == old_cues


@pytest.mark.parametrize("events", [[], [{"start_ms": 5833, "end_ms": 6000, "text": "Terakhir"}]])
def test_empty_or_clip_end_word_events_keep_exact_timing(adapter, events):
    adapter["snapshot"]["subtitle_events"] = events
    if not events:
        adapter["snapshot"]["cues"] = []
    result = invoke(adapter)
    manifest = adapter["captured"]["node"][2]
    assert manifest["cues"] == events and manifest["durationMs"] == 6000
    assert manifest["style"]["display_mode"] == "words"
    assert result["mp4"].is_file()


def test_sentence_mode_uses_original_cues_when_word_events_are_absent(adapter):
    adapter["snapshot"].pop("subtitle_events")
    adapter["snapshot"]["subtitle_style_json"]["display_mode"] = "sentence"
    invoke(adapter)
    assert adapter["captured"]["node"][2]["cues"] == adapter["snapshot"]["cues"]


@pytest.mark.parametrize("failure", ["cancel", "nonzero", "missing_output", "missing_node"])
def test_failure_never_falls_back_or_publishes_and_removes_intermediate_video(adapter, monkeypatch, failure):
    def run(args, **options):
        manifest = json.loads(Path(args[-1]).read_text())
        if failure != "missing_output":
            Path(manifest["outputPath"]).write_bytes(b"partial")
        if failure == "cancel":
            raise Cancelled()
        if failure == "missing_node":
            raise FileNotFoundError("node")
        return ProcessResult("", "test failure", 1 if failure == "nonzero" else 0)
    monkeypatch.setattr(remotion, "run_process", run)
    with pytest.raises(MediaError) as exc:
        invoke(adapter)
    expected = {"cancel": "cancelled", "missing_node": "remotion_unavailable"}.get(failure, "remotion_render_failed")
    assert exc.value.code == expected
    assert "mux" not in adapter["captured"]
    assert not list(adapter["directory"].rglob("*.mp4"))


@pytest.mark.parametrize("changes", [{"audio_codec": None}, {"width": 1080}, {"duration_ms": 6200}, {"fps": 24}])
def test_invalid_final_media_is_not_published(adapter, changes):
    adapter["meta"].update(changes)
    with pytest.raises(MediaError, match="Hasil Remotion") as exc:
        invoke(adapter)
    assert exc.value.code == "invalid_render"
    assert not list(adapter["directory"].rglob("*.mp4"))


def test_queued_version_is_checked_before_preparation(adapter):
    adapter["config"]["renderer_version"] = "previous"
    with pytest.raises(MediaError) as exc:
        invoke(adapter)
    assert exc.value.code == "remotion_version_changed"
    assert not adapter["captured"]


def test_renderer_diagnostics_do_not_log_caption_text_or_serialized_metadata(adapter, monkeypatch, caplog):
    secret_caption = "PRIVATE_CAPTION_SHOULD_NOT_APPEAR"
    monkeypatch.setattr(remotion, "run_process", lambda *args, **options: ProcessResult("", secret_caption, 1))
    with pytest.raises(MediaError) as exc:
        invoke(adapter)
    assert secret_caption not in caplog.text and secret_caption not in exc.value.message
    assert "exit=1" in caplog.text


def test_legacy_config_defaults_to_ffmpeg_even_without_renderer_fields(monkeypatch):
    captured = []
    monkeypatch.setattr(render, "_render_ffmpeg", lambda *args, **options: captured.append((args, options)) or "legacy")
    assert render.render_clip("source", "scratch", {}, {"width": 720}) == "legacy"
    assert len(captured) == 1


def test_render_dispatch_delegates_remotion_and_runtime_options(monkeypatch):
    captured = []
    monkeypatch.setattr(remotion, "render_remotion", lambda *args, **options: captured.append((args, options)) or "remotion")
    config = {"renderer": "remotion", "renderer_version": remotion.REMOTION_RENDERER_VERSION}
    assert render.render_clip("source", "scratch", {}, config, remotion_node_path="runtime-node", remotion_script_path="runtime-script") == "remotion"
    assert captured[0][1]["node_path"] == "runtime-node"
    assert captured[0][1]["script_path"] == "runtime-script"
    assert captured[0][1]["prepare"] is render._render_ffmpeg
