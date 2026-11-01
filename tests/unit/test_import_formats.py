from yt_dlp import YoutubeDL

from app.media.import_formats import shortlist_formats


def video(identifier, width, height, codec="avc1.640028", **kwargs):
    return {"format_id": identifier, "width": width, "height": height, "vcodec": codec,
            "acodec": "none", "protocol": "https", "ext": "mp4", "url": f"https://video.example/{identifier}", **kwargs}


def audio(identifier="audio", **kwargs):
    return {"format_id": identifier, "vcodec": "none", "acodec": "mp4a.40.2",
            "protocol": "https", "ext": "m4a", "url": f"https://video.example/{identifier}", **kwargs}


def selected(formats, **kwargs):
    return {f["format_id"] for f in shortlist_formats(formats, max_width=3840, max_height=2160, **kwargs)}


def download_selection(formats):
    shortlist = shortlist_formats(formats, max_width=3840, max_height=2160, target_height=1080)
    with YoutubeDL({"quiet": True, "no_warnings": True}) as downloader:
        selector = downloader.build_format_selector("bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b")
        return list(selector({"formats": shortlist, "has_merged_format": False, "incomplete_formats": False}))


def test_cap_4k_at_1080_and_prefer_same_resolution_avc_while_preserving_audio():
    formats = [video("4k-av1", 3840, 2160, "av01"), video("1080-av1", 1920, 1080, "av01"),
               video("1080-avc", 1920, 1080), video("720-avc", 1280, 720), audio()]
    assert selected(formats, target_height=1080) == {"1080-avc", "audio"}


def test_portrait_uses_equivalent_short_side_and_keeps_audio_without_dimensions():
    formats = [video("portrait", 1080, 1920), video("portrait-4k", 2160, 3840), audio(), audio("opus", acodec="opus", ext="webm")]
    assert selected(formats, target_height=1080) == {"portrait", "audio", "opus"}


def test_higher_quality_non_avc_is_not_replaced_by_small_mp4_stream():
    # yt-dlp's MP4-first selector must not be handed a tiny AVC alternative
    # when the only full-resolution choice is WebM/VP9.
    formats = [video("360-avc", 640, 360), video("1080-vp9", 1920, 1080, "vp9", ext="webm"), audio()]
    assert selected(formats, target_height=1080) == {"1080-vp9", "audio"}


def test_single_high_resolution_source_remains_usable_when_no_capped_option_exists():
    assert selected([video("only-4k", 3840, 2160, "av01"), audio()], target_height=1080) == {"only-4k", "audio"}


def test_limits_drm_and_external_download_protocols_stay_excluded():
    formats = [video("valid", 1920, 1080), audio(), video("drm", 1920, 1080, has_drm=True),
               video("rtmp", 1920, 1080, protocol="rtmp"), video("8k", 7680, 4320)]
    assert selected(formats) == {"valid", "audio"}


def test_actual_downloader_selector_uses_full_resolution_non_avc_with_audio():
    result = download_selection([video("360-avc", 640, 360), video("1080-vp9", 1920, 1080, "vp9", ext="webm"), audio()])
    assert len(result) == 1
    assert [f["format_id"] for f in result[0]["requested_formats"]] == ["1080-vp9", "audio"]


def test_actual_downloader_selector_uses_capped_avc_and_retains_audio_stream():
    result = download_selection([video("1080-avc", 1920, 1080), video("4k-av1", 3840, 2160, "av01"), audio()])
    assert [f["format_id"] for f in result[0]["requested_formats"]] == ["1080-avc", "audio"]


def test_actual_downloader_selector_retains_progressive_mp4_audio():
    result = download_selection([video("progressive", 1920, 1080, acodec="mp4a.40.2")])
    assert len(result) == 1 and result[0]["format_id"] == "progressive"
    assert result[0]["acodec"] == "mp4a.40.2"
