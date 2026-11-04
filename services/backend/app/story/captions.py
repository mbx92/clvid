"""Caption timing shared conceptually with Remotion's story-captions.ts."""
import math


def has_timed_captions(scene):
    """Audio/narration changes invalidate old alignment without losing the edit."""
    return bool(scene.get("captions") and scene.get("audio_id")
                and scene.get("caption_audio_id") == scene["audio_id"]
                and scene.get("caption_narration") == scene["narration"])


def scene_captions(scene, fps=30):
    if not scene.get("show_caption", True):
        return []
    if has_timed_captions(scene):
        return [dict(cue) for cue in scene["captions"]]
    chunks = []
    for word in scene["narration"].split():
        # JS counts UTF-16 units; keep the legacy fallback identical in exports.
        length = lambda text: len(text.encode("utf-16-le")) // 2
        if not chunks or length(chunks[-1]) + length(word) + 1 > 70:
            chunks.append(word)
        else:
            chunks[-1] += " " + word
    frames = round(scene["duration_ms"] * fps / 1000)
    return [{"start_ms": round(math.ceil(i * frames / len(chunks)) * 1000 / fps),
             "end_ms": round(math.ceil((i + 1) * frames / len(chunks)) * 1000 / fps),
             "text": text} for i, text in enumerate(chunks)]


def story_captions(document):
    result, start = [], 0
    for scene in document["scenes"]:
        result.extend({**cue, "start_ms": start + cue["start_ms"],
                       "end_ms": start + cue["end_ms"]} for cue in scene_captions(scene))
        start += scene["duration_ms"]
    return result
