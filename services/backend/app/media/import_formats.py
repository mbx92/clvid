def shortlist_formats(formats, *, max_width, max_height, target_height=1080):
    audio, video, unknown = [], [], []
    limits = sorted((max_width, max_height))
    for fmt in formats:
        if fmt.get("has_drm") or fmt.get("protocol") not in ("http", "https", "m3u8_native", "http_dash_segments"):
            continue
        if fmt.get("vcodec") == "none":
            audio.append(fmt)
        elif not fmt.get("width") or not fmt.get("height"):
            # Direct MP4 URLs often have no extractor metadata. The downloaded
            # bytes still undergo the normal size/duration/resolution checks.
            unknown.append(fmt)
        elif fmt.get("width") and fmt.get("height") and all(a <= b for a, b in zip(sorted((fmt["width"], fmt["height"])), limits)):
            video.append(fmt)
    if not video:
        return audio + unknown
    capped = [v for v in video if min(v["width"], v["height"]) <= target_height] or video
    quality = max(min(v["width"], v["height"]) for v in capped)
    best = [v for v in capped if min(v["width"], v["height"]) == quality]
    avc = [v for v in best if v.get("vcodec", "").startswith(("avc", "h264"))]
    return audio + (avc or best)
