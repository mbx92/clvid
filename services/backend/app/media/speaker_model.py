"""Bounded-window Light-ASD inference using the bundled model's PCM16 contract."""
from dataclasses import dataclass
import math
from pathlib import Path
import wave

import cv2
import numpy as np

from .process import Cancelled, MediaError


def mfcc_pcm16(samples):
    samples = np.asarray(samples, dtype=np.float64)
    if not len(samples):
        raise ValueError("Empty audio")
    emphasized = np.append(samples[0], samples[1:] - .97*samples[:-1])
    count = 1 + max(0, math.ceil((len(samples)-400)/160))
    padded = np.pad(emphasized, (0, (count-1)*160+400-len(samples)))
    frames = padded[np.arange(count)[:, None]*160 + np.arange(400)[None, :]]
    power = np.abs(np.fft.rfft(frames, 512))**2/512
    epsilon = np.finfo(float).eps
    energy = np.maximum(power.sum(axis=1), epsilon)
    frequencies = 700*(10**(np.linspace(0, 2595*np.log10(1+8000/700), 28)/2595)-1)
    bins = np.floor(513*frequencies/16000).astype(int)
    bank = np.zeros((26, 257))
    for row in range(26):
        left, middle, right = bins[row:row+3]
        bank[row, left:middle] = np.arange(middle-left)/(middle-left)
        bank[row, middle:right] = (right-np.arange(middle, right))/(right-middle)
    logbank = np.log(np.maximum(power @ bank.T, epsilon))
    dct = np.cos(np.pi/26 * (np.arange(26)+.5)[:, None]*np.arange(13)[None, :])*np.sqrt(2/26)
    dct[:, 0] /= np.sqrt(2)
    features = (logbank @ dct)*(1+11*np.sin(np.pi*np.arange(13)/22))
    features[:, 0] = np.log(energy)
    return features


def _median13(values):
    return np.median(np.lib.stride_tricks.sliding_window_view(np.pad(values, (6, 6)), 13), axis=-1)


def _face_crop(image, center):
    x, y, size = center
    size = max(1., size)
    padding = int(size*1.8)
    padded = np.pad(image, ((padding, padding), (padding, padding), (0, 0)), constant_values=110)
    crop = padded[int(y+padding-size):int(y+padding+size*1.8), int(x+padding-size*1.4):int(x+padding+size*1.4)]
    if not crop.size:
        raise MediaError("speaker_inference_failed", "Area wajah tidak dapat dibaca.")
    return cv2.cvtColor(cv2.resize(crop, (224, 224)), cv2.COLOR_BGR2GRAY)[56:168, 56:168]


@dataclass
class Track:
    identity: int
    start: int
    stop: int
    centers: np.ndarray


def _tracks(observations, width, height, frame_count):
    groups, active = [], {}
    previous = -1
    for row in observations:
        if row["t_ms"] < previous:
            raise MediaError("speaker_inference_failed", "Urutan waktu wajah tidak valid.")
        previous = row["t_ms"]
        if row.get("cut"):
            groups.extend(active.values())
            active = {}
        frame = min(frame_count-1, round(row["t_ms"]/40))
        for face in row["faces"]:
            identity = face["id"]
            group = active.get(identity)
            if group and frame-group[-1][0] > 20:
                groups.append(group)
                group = None
            if group is None:
                group = active[identity] = []
            x, y, w, h = face["box"]
            center = ((x+w/2)*width, (y+h/2)*height, max(w*width, h*height)/2)
            group.append((frame, identity, center))
    groups.extend(active.values())
    result = []
    for group in groups:
        if len(group) < 2 or group[-1][0] <= group[0][0]:
            continue
        start, stop = group[0][0], group[-1][0]+1
        times = np.array([row[0] for row in group])
        centers = np.array([row[2] for row in group])
        interpolated = np.column_stack([_median13(np.interp(np.arange(start, stop), times, centers[:, axis])) for axis in range(3)])
        result.append(Track(group[0][1], start, stop, interpolated))
    return sorted(result, key=lambda track: (track.start, track.identity))


def _window_count(count):
    return max(1, 1+math.ceil((count-100)/50))


def _infer(session, audio_name, video_name, features, faces):
    count = len(faces)
    length = max(25, count)
    video = np.asarray(faces, dtype=np.float32)
    video = np.pad(video, ((0, length-count), (0, 0), (0, 0)), mode="edge")
    features = np.asarray(features, dtype=np.float32)
    if not len(features):
        raise ValueError("Audio missing")
    features = np.pad(features[:length*4], ((0, max(0, length*4-len(features))), (0, 0)), mode="edge")
    logits = np.asarray(session.run(None, {audio_name: features[None], video_name: video[None]})[0])
    if logits.shape != (length, 2) or not np.isfinite(logits).all():
        raise ValueError("Invalid model output")
    difference = np.clip(logits[:count, 1]-logits[:count, 0], -80, 80)
    return 1/(1+np.exp(-difference))


def score_speakers(video, audio, observations, model, progress=None, cancelled=None):
    if cancelled and cancelled():
        raise Cancelled()
    if not Path(model).is_file():
        raise MediaError("speaker_model_missing", "Model audiovisual belum tersedia.")
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened() or abs(capture.get(cv2.CAP_PROP_FPS)-25) > .05:
            raise MediaError("invalid_speaker_video", "Analisis pembicara memerlukan video 25 fps.")
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        tracks = _tracks(observations, width, height, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        if not tracks:
            return {}
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        audio_name, video_name = [value.name for value in session.get_inputs()]
        total = sum(_window_count(t.stop-t.start) for t in tracks)
        completed, result = 0, {}
        with wave.open(str(audio), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getframerate() != 16000 or wav.getsampwidth() != 2:
                raise ValueError("Invalid PCM")
            for track in tracks:
                count = track.stop-track.start
                sums, weights = np.zeros(count), np.zeros(count)
                for index in range(_window_count(count)):
                    if cancelled and cancelled():
                        raise Cancelled()
                    start, stop = index*50, min(count, index*50+100)
                    capture.set(cv2.CAP_PROP_POS_FRAMES, track.start+start)
                    faces = []
                    for frame in range(start, stop):
                        ok, image = capture.read()
                        if not ok:
                            raise ValueError("Video ended early")
                        faces.append(_face_crop(image, track.centers[frame]))
                    wav.setpos(min(wav.getnframes(), (track.start+start)*640))
                    samples = np.frombuffer(wav.readframes((stop-start)*640), dtype="<i2")
                    values = _infer(session, audio_name, video_name, mfcc_pcm16(samples), faces)
                    sums[start:stop] += values
                    weights[start:stop] += 1
                    completed += 1
                    if progress:
                        progress(completed/total)
                probabilities = sums/np.maximum(weights, 1)
                for i, row in enumerate(observations):
                    frame = round(row["t_ms"]/40)
                    if track.start <= frame < track.stop and any(f["id"] == track.identity for f in row["faces"]):
                        result[i, track.identity] = float(probabilities[frame-track.start])
        return result
    except (Cancelled, MediaError):
        raise
    except Exception as exc:
        raise MediaError("speaker_inference_failed", "Model audiovisual gagal menganalisis video.") from exc
    finally:
        capture.release()
