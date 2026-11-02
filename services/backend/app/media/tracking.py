from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

from .process import Cancelled, MediaError, ffmpeg, run_process
from .tracking_versions import SAMPLE_FPS


def crop_for_face(face, aspect):
    x, y, w, h = face["box"]
    horizontal = min(1, (9/16)/aspect)
    vertical = min(1, aspect/(9/16))
    return (max(0, min(1, (x+w/2-horizontal/2)/(1-horizontal))) if horizontal < 1 else .5,
            max(0, min(1, (face.get("eyes_y", y+h/2)-vertical*.35)/(1-vertical))) if vertical < 1 else .5)


class FaceAssociator:
    def __init__(self):
        self.next_id, self.tracks = 1, {}

    def reset(self):
        self.tracks.clear()

    def update(self, boxes, t_ms):
        self.tracks = {i: value for i, value in self.tracks.items() if t_ms-value[1] <= 800}
        used, result = set(), []
        for box in boxes:
            x, y, w, h = box
            choices = []
            for identity, (old, _) in self.tracks.items():
                if identity in used:
                    continue
                ox, oy, ow, oh = old
                distance = math.hypot(x+w/2-ox-ow/2, y+h/2-oy-oh/2)
                if distance < max(w, h, ow, oh)*.7:
                    choices.append((distance, identity))
            identity = min(choices)[1] if choices else self.next_id
            if not choices:
                self.next_id += 1
            self.tracks[identity] = (box, t_ms)
            used.add(identity)
            result.append(identity)
        return result


class CropPlanner:
    def __init__(self, mode, aspect, fallback):
        self.mode, self.aspect, self.fallback = mode, aspect, fallback
        self.position = None
        self.target_id = None
        self.last_seen = 0
        self.speaker_switches = 0
        self.challenger, self.since = None, 0

    def step(self, t_ms, faces, audio_active, shot_cut=False):
        first = self.position is None
        target = next((f for f in faces if f["id"] == self.target_id), None)
        if faces and (target is None or shot_cut):
            target = max(faces, key=lambda f: f["box"][2]*f["box"][3])
            self.target_id = target["id"]
        # Legacy planner API; production speaker paths use audiovisual scores
        # through ActiveSpeakerSelector, never this motion signal.
        if self.mode == "speaker" and audio_active and faces:
            best = max(faces, key=lambda f: f.get("activity", 0))
            if best["id"] != self.target_id and best.get("activity", 0) > .03:
                if self.challenger != best["id"]:
                    self.challenger, self.since = best["id"], t_ms
                elif t_ms-self.since >= 600:
                    target, self.target_id = best, best["id"]
                    self.speaker_switches += 1
                    shot_cut = True
            else:
                self.challenger = None
        if target:
            desired = crop_for_face(target, self.aspect)
            self.last_seen = t_ms
        elif first or t_ms-self.last_seen > 1000:
            desired = self.fallback
        else:
            desired = self.position
        self.position = desired if first or shot_cut else tuple(a+(b-a)*.45 for a, b in zip(self.position, desired))
        return dict(t_ms=t_ms, x=self.position[0], y=self.position[1], cut=bool(first or shot_cut))


def write_tracking_commands(path, keyframes):
    lines = []
    for index, frame in enumerate(keyframes):
        following = keyframes[index+1] if index+1 < len(keyframes) else None
        expressions = []
        for axis, extent in (("x", "iw-ow"), ("y", "ih-oh")):
            expr = f"({extent})*{frame[axis]:.6f}"
            if following and not following.get("cut", False):
                duration = (following["t_ms"]-frame["t_ms"])/1000
                expr = f"({extent})*({frame[axis]:.6f}+({following[axis]-frame[axis]:.6f})*(t-{frame['t_ms']/1000:.3f})/{duration:.3f})"
            expressions.append(f"crop {axis} '{expr}'")
        lines.append(f"{frame['t_ms']/1000:.3f} " + ", ".join(expressions) + ";")
    Path(path).write_text("\n".join(lines)+"\n", encoding="utf-8")


def track_clip(source, directory, *, start_ms, end_ms, crop, ffmpeg_bin="ffmpeg",
               model_path=None, speaker_model_path=None, sample_fps=SAMPLE_FPS,
               timeout=14400, cancelled=None, progress=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    mode, duration = crop.get("tracking", "face"), end_ms-start_ms
    fallback = dict(mode=mode, method="manual", detected_frames=0, total_frames=0, warnings=[],
                    keyframes=[dict(t_ms=0, x=crop.get("x", .5), y=crop.get("y", .5), cut=True)])
    def failure(reason):
        return {**fallback, "fallback_reason": reason}
    if cancelled and cancelled():
        raise Cancelled()
    if not model_path or not Path(model_path).is_file():
        return failure("Model wajah belum tersedia; posisi manual digunakan.")
    if mode == "speaker" and (not speaker_model_path or not Path(speaker_model_path).is_file()):
        return failure("Model audiovisual belum tersedia; posisi manual digunakan.")
    try:
        video, audio = directory/"tracking.avi", directory/"tracking.wav"
        fps = 25 if mode == "speaker" else sample_fps
        common = ["-protocol_whitelist", "file,pipe", "-ss", str(start_ms/1000), "-i", str(source), "-t", str(duration/1000)]
        ffmpeg([*common, "-vf", f"scale='min(640,iw*sar)':-2,setsar=1,fps={fps}", "-an", "-c:v", "mjpeg", "-q:v", "3", "-threads", "2", str(video)],
               binary=ffmpeg_bin, timeout=timeout, cancelled=cancelled)
        if mode == "speaker":
            ffmpeg([*common, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)],
                   binary=ffmpeg_bin, timeout=timeout, cancelled=cancelled)
        request, output = directory/"tracking-input.json", directory/"tracking-output.json"
        config = dict(source=str(video.resolve()), audio=str(audio.resolve()), output=str(output.resolve()),
                      model=str(Path(model_path).resolve()), mode=mode, duration_ms=duration,
                      fallback=[crop.get("x", .5), crop.get("y", .5)], sample_fps=sample_fps,
                      model_sha256=hashlib.sha256(Path(model_path).read_bytes()).hexdigest(),
                      speaker_model=str(Path(speaker_model_path).resolve()) if mode == "speaker" else None,
                      speaker_model_sha256=hashlib.sha256(Path(speaker_model_path).read_bytes()).hexdigest() if mode == "speaker" else None)
        request.write_text(json.dumps(config), encoding="utf-8")
        result = run_process([sys.executable, "-m", "app.media.tracking_child", str(request.resolve())],
                             timeout=timeout, cancelled=cancelled, progress=progress, duration_ms=duration)
        if result.returncode or not output.exists():
            return failure("Pelacakan tidak dapat diselesaikan; posisi manual digunakan.")
        return json.loads(output.read_text(encoding="utf-8"))
    except Cancelled:
        raise
    except (MediaError, OSError, ValueError):
        return failure("Pelacakan tidak dapat diselesaikan; posisi manual digunakan.")
