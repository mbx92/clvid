from .process import MediaError


def normalized(text):
    return "".join(c.casefold() for c in text if c.isalnum())


def align_words(cues, words, clip_start_ms):
    events, missing = [], 0
    for cue in cues:
        candidates = [w for w in words if w["end_ms"] > cue["start_ms"] + clip_start_ms
                      and w["start_ms"] < cue["end_ms"] + clip_start_ms]
        if (not candidates or any(w["end_ms"] <= w["start_ms"] for w in candidates)
                or any(a["end_ms"] > b["start_ms"] for a, b in zip(candidates, candidates[1:]))):
            missing += 1
            continue
        # Keep ASR token boundaries (including multiword tokens); join only
        # continuation tokens which have no leading space.
        groups = []
        for w in candidates:
            if groups and w["word"][:1] and not w["word"][0].isspace() and w["word"].startswith(("-", "'", "’")):
                groups[-1]["word"] += w["word"]
                groups[-1]["end_ms"] = w["end_ms"]
            else:
                groups.append(dict(w))
        text = cue["text"]
        if normalized(text) != normalized("".join(w["word"] for w in groups)):
            missing += 1
            continue
        positions = [i for i, char in enumerate(text) if char.isalnum() for _ in char.casefold()]
        offset, local = 0, []
        for i, w in enumerate(groups):
            count = len(normalized(w["word"]))
            if not count:
                continue
            start = positions[offset] if offset else 0
            offset += count
            stop = positions[offset] if offset < len(positions) else len(text)
            a = max(cue["start_ms"], w["start_ms"] - clip_start_ms)
            b = min(cue["end_ms"], w["end_ms"] - clip_start_ms)
            if b > a:
                local.append(dict(start_ms=a, end_ms=b, text=text[start:stop].strip()))
        events.extend(local)
    return events, missing


def word_events(cues, words, clip_start_ms):
    events, missing = align_words(cues, words, clip_start_ms)
    if missing:
        raise MediaError("subtitle_word_timing", "Subtitle tidak memiliki timestamp kata yang cocok; gunakan mode kalimat atau transkripsikan kembali.")
    return events
