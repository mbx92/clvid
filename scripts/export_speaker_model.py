"""Reproduce the bundled MIT Light-ASD model with a development-only Torch install.

Dependencies: torch==2.10.0 (CPU), onnx==1.20.1, onnxruntime==1.31.1, numpy.
Runtime inference uses ONNX Runtime, never Torch or pickle. Downloads are pinned
to an upstream commit and verified before importing code/loading tensor weights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'ed38c232de5efe0261dbd68627c0ade7cdfe14eb'
BASE = f'https://raw.githubusercontent.com/Junhua-Liao/Light-ASD/{COMMIT}/'
FILES = {
    'LICENSE': '3c5b187c06d6c0fdcfe02ad73f51470eaa35045cc2e60749d805332d98441eb1',
    'model/Model.py': '6094bfaab7d5a701e1580ee6ec89c7cfea2baacf62b3ceafff5558f31dd3fc8d',
    'model/Encoder.py': 'c4a85b8aa5eaab428f79836c5d9511a01ac45bfeb6dccc75e06c1e9eff25520c',
    'model/Classifier.py': '21fdebc3c08ee3a386111719035f06461b29548b9b900eff3e17e4083f4377f8',
    'weight/finetuning_TalkSet.model': 'efc375833887eefa9d209dc92810e18519b04c3c73ea35a549f2a7f40b7d94d5',
    'weight/pretrain_AVA_CVPR.model': 'd44bc3ea7baa8e0946fa3921311714a630ed8b90a1928fab0dbe30d918909317',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=ROOT / '.tools/light-asd-upstream')
    parser.add_argument('--variant', choices=['talkset', 'ava'], default='talkset')
    parser.add_argument('--output', type=Path, default=ROOT / 'services/backend/models/light_asd_talkset.onnx')
    args = parser.parse_args()
    for name, checksum in FILES.items():
        path = args.work_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            path.write_bytes(urllib.request.urlopen(BASE + name, timeout=90).read())
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Upstream checksum mismatch: {name}')
    sys.path.insert(0, str(args.work_dir.resolve()))
    import numpy as np
    import torch
    from torch import nn
    import onnx
    import onnxruntime as ort
    from model.Model import ASD_Model
    torch.set_num_threads(2)
    torch.manual_seed(0)

    class Inference(nn.Module):
        def __init__(self):
            super().__init__()
            self.model = ASD_Model()
            self.lossAV = nn.Module()
            self.lossAV.FC = nn.Linear(128, 2)

        def forward(self, audio, video):
            audio = self.model.forward_audio_frontend(audio)
            visual = self.model.forward_visual_frontend(video)
            fused = self.model.forward_audio_visual_backend(audio, visual)
            return self.lossAV.FC(fused)

    network = Inference().eval()
    weight_name = 'weight/finetuning_TalkSet.model' if args.variant == 'talkset' else 'weight/pretrain_AVA_CVPR.model'
    weights = torch.load(args.work_dir / weight_name, map_location='cpu', weights_only=True)
    wanted = network.state_dict()
    network.load_state_dict({name: weights[name] for name in wanted}, strict=True)
    audio = torch.randn(1, 200, 13)
    video = torch.rand(1, 50, 112, 112) * 255
    with torch.inference_mode():
        reference = network(audio, video).numpy()
    # Upstream uses MaxPool3d on unbatched 4D audio. This equivalent 2D form
    # exports without rank ambiguity and introduces no change to the weights.
    network.model.audioEncoder.pool1 = nn.MaxPool2d((1, 3), (1, 2), (0, 1))
    network.model.audioEncoder.pool2 = nn.MaxPool2d((1, 3), (1, 2), (0, 1))
    with torch.inference_mode():
        np.testing.assert_array_equal(network(audio, video).numpy(), reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(network, (audio, video), str(args.output),
                      input_names=['audio', 'video'], output_names=['logits'],
                      dynamic_axes={'audio': {1: 'audio_frames'}, 'video': {1: 'video_frames'}, 'logits': {0: 'video_frames'}},
                      opset_version=17, dynamo=False, external_data=False)
    onnx.checker.check_model(onnx.load(args.output))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(args.output), options, providers=['CPUExecutionProvider'])
    errors = []
    for frames in (25, 50, 100):
        audio = torch.randn(1, frames * 4, 13)
        video = torch.rand(1, frames, 112, 112) * 255
        with torch.inference_mode():
            expected = network(audio, video).numpy()
        actual = session.run(None, {'audio': audio.numpy(), 'video': video.numpy()})[0]
        np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)
        errors.append({'frames': frames, 'max_absolute_error': float(np.max(np.abs(actual - expected)))})
    manifest = {'upstream': 'https://github.com/Junhua-Liao/Light-ASD', 'commit': COMMIT,
                'license': 'MIT', 'weight': weight_name, 'weight_sha256': FILES[weight_name],
                'onnx_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                'onnx_bytes': args.output.stat().st_size, 'torch': torch.__version__, 'opset': 17,
                'input': {'audio': 'float32[1,4*T,13] MFCC, PCM16', 'video': 'float32[1,T,112,112] grayscale0–255'},
                'output': 'float32[T,2] logits; speaking probability=softmax(logits)[:,1]', 'parity': errors}
    args.output.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
