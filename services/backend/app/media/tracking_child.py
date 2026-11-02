import json
from pathlib import Path
import sys
import wave

import cv2
import numpy as np

from .tracking import CropPlanner, FaceAssociator
from .tracking_versions import TRACKING_METHODS
from .speaker_model import score_speakers
from .speaker_tracking import plan_speaker_crop


def analyze(config):
    cv2.setNumThreads(2)
    capture = cv2.VideoCapture(config["source"])
    if not capture.isOpened():
        raise ValueError("Video unreadable")
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    detector = cv2.FaceDetectorYN.create(config["model"], "", (width, height), .75, .3, 5000)
    associator = FaceAssociator()
    observations, previous, next_sample, index = [], None, 0, 0
    samples = None
    if config["mode"] == "speaker":
        with wave.open(config["audio"], "rb") as wav:
            samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            t = round(index*1000/fps)
            index += 1
            if t+1 < next_sample or t >= config["duration_ms"]:
                continue
            next_sample += 1000/config["sample_fps"]
            thumbnail = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36)).astype(float)
            cut = previous is not None and np.mean(np.abs(thumbnail-previous)) > 45
            previous = thumbnail
            if cut:
                associator.reset()
            _, detected = detector.detect(frame)
            boxes, eyes = [], []
            for face in detected if detected is not None else []:
                x, y, w, h = face[:4]
                boxes.append((float(max(0, x)/width), float(max(0, y)/height), float(min(w, width-x)/width), float(min(h, height-y)/height)))
                eyes.append(float((face[5]+face[7])/2/height))
            ids = associator.update(boxes, t)
            audio_active = False
            if samples is not None:
                window = samples[max(0, int(t*16)):int((t+160)*16)].astype(float)
                audio_active = bool(len(window) and np.sqrt(np.mean(window**2)) > 180)
            observations.append(dict(t_ms=t, cut=bool(cut), audio_active=audio_active,
                                     faces=[dict(id=identity, box=box, eyes_y=eye) for identity, box, eye in zip(ids, boxes, eyes)]))
            print(f"segment_end_ms={round(t*.4 if samples is not None else t)}", flush=True)
    finally:
        capture.release()
    if not observations:
        raise ValueError("No decoded frames")
    if config["mode"] == "speaker":
        scores = score_speakers(config["source"], config["audio"], observations, config["speaker_model"],
                                progress=lambda amount: print(f"segment_end_ms={round(config['duration_ms']*(.4+.6*amount))}", flush=True))
        path, switches = plan_speaker_crop(observations, scores, aspect=width/height, fallback=config["fallback"], duration_ms=config["duration_ms"])
    else:
        planner = CropPlanner("face", width/height, config["fallback"])
        path = [planner.step(row["t_ms"], row["faces"], False, shot_cut=row["cut"]) for row in observations]
        path.append({**path[-1], "t_ms": config["duration_ms"], "cut": False})
        switches = 0
    detected = sum(bool(row["faces"]) for row in observations)
    return dict(mode=config["mode"], method=TRACKING_METHODS[config["mode"]], sample_fps=config["sample_fps"],
                model_sha256=config["model_sha256"], speaker_model_sha256=config["speaker_model_sha256"],
                keyframes=path, total_frames=len(observations), detected_frames=detected, speaker_switches=switches,
                warnings=[], fallback_reason=None if detected else "Wajah tidak terdeteksi; posisi manual digunakan.")


if __name__ == "__main__":
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    Path(config["output"]).write_text(json.dumps(analyze(config)), encoding="utf-8")
