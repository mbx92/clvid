from copy import deepcopy
from .gaming import finite
from .tracking import CropPlanner


class ActiveSpeakerSelector:
    def __init__(self):
        self.target_id = None
        self.switches = 0
        self.evidence = {}
        self.last_t = None
        self.last_switch = 0
        self.last_audio = 0

    def step(self, t_ms, faces, audio_active, shot_cut=False):
        delta = min(200, max(0, t_ms-self.last_t)) if self.last_t is not None else 0
        self.last_t = t_ms
        scores = {f["id"]: f.get("speaker_score", 0) if finite(f.get("speaker_score"), 0, 1) else 0 for f in faces}
        if shot_cut:
            self.target_id = None
            self.evidence = {}
        if self.target_id is None or self.target_id not in scores:
            if faces:
                best = max(faces, key=lambda f: (scores[f["id"]] if audio_active else 0, f["box"][2]*f["box"][3]))
                self.target_id, self.last_switch = best["id"], t_ms
            return self.target_id
        if not audio_active:
            if t_ms-self.last_audio > 400:
                self.evidence = {}
            return self.target_id
        self.last_audio = t_ms
        challenger = max(scores, key=scores.get)
        if challenger != self.target_id and scores[challenger] >= .65 and scores[challenger]-scores[self.target_id] >= .2:
            self.evidence = {challenger: self.evidence.get(challenger, 0)+delta}
            if self.evidence[challenger] >= 400 and t_ms-self.last_switch >= 900:
                self.target_id, self.last_switch = challenger, t_ms
                self.switches += 1
                self.evidence = {}
        else:
            self.evidence = {}
        return self.target_id


def plan_speaker_crop(observations, scores, *, aspect, fallback, duration_ms):
    selector, planner = ActiveSpeakerSelector(), CropPlanner("face", aspect, fallback)
    path, previous = [], None
    for index, row in enumerate(observations):
        faces = deepcopy(row["faces"])
        for face in faces:
            face["speaker_score"] = scores.get((index, face["id"]), 0)
        selected = selector.step(row["t_ms"], faces, row.get("audio_active", False), row.get("cut", False))
        path.append(planner.step(row["t_ms"], [f for f in faces if f["id"] == selected], row.get("audio_active", False),
                                 shot_cut=row.get("cut", False) or (previous is not None and selected != previous)))
        previous = selected
    if not path:
        path = [dict(t_ms=0, x=fallback[0], y=fallback[1], cut=True)]
    if path[-1]["t_ms"] < duration_ms:
        path.append({**path[-1], "t_ms": duration_ms, "cut": False})
    return path, selector.switches
