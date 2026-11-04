"""Install pinned, public local speech weights without a Hugging Face token.

Model CC BY 4.0: anak10thn / Pocket TTS Indonesian, based on Kyutai Pocket TTS
and the LEMAS Project. The two included Common Voice 22.0 voice prompts are CC0.
This script downloads files only; generation never contacts the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


REPO = 'anak10thn/pocket-tts-indonesian'
REVISION = '382fe85ca848546efb04bf1b7fdba78c6396e2ce'
FILES = {
    '6l/model.safetensors': ('model.safetensors', '3b9e74387594d12737fce7e2b34eea249ebc57ae6cb3d157c7ec3a21fb475bf2'),
    'tokenizer.model': ('tokenizer.model', '3ae0af2658bf8f54c6720603b4d965cad97d67cb0f245636d0eb23ff4f865fd8'),
    'voices/common_voice_id_19961910.mp3': ('voices/common_voice_id_19961910.mp3', None),
    'voices/common_voice_id_20954552.mp3': ('voices/common_voice_id_20954552.mp3', None),
    'README.md': ('MODEL_CARD.md', None),
    'voices/README.md': ('voices/README.md', None),
    'indonesian_6l.yaml': ('upstream-config.yaml', None),
}


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            checksum.update(block)
    return checksum.hexdigest()


def download(root):
    directory = root / 'speech' / 'pocket-id'
    directory.mkdir(parents=True, exist_ok=True)
    for remote, (name, checksum) in FILES.items():
        target = directory / name
        if target.is_file() and (not checksum or digest(target) == checksum):
            print('Already installed:', name, flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.partial')
        request = urllib.request.Request(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{remote}', headers={'User-Agent':'Clipper-local-model-installer/1'})
        print('Downloading:', name, flush=True)
        try:
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open('wb') as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            if checksum and digest(temporary) != checksum:
                raise RuntimeError(f'Checksum mismatch: {name}')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    # JSON is valid YAML; keep only local paths and preserve the pinned model config.
    # The child resolves relative paths before loading; no runtime download is used.
    config = {
        'weights_path': 'model.safetensors', 'default_temperature': 0.3,
        'flow_lm': {'insert_bos_before_voice': True, 'dtype':'float32',
                    'flow': {'depth':6, 'dim':512},
                    'transformer': {'d_model':1024, 'hidden_scale':4, 'max_period':10000, 'num_heads':16, 'num_layers':6},
                    'lookup_table': {'dim':1024, 'n_bins':4000, 'tokenizer':'sentencepiece', 'tokenizer_path':'tokenizer.model'}},
        'mimi': {'dtype':'float32', 'sample_rate':24000, 'inner_dim':32, 'outer_dim':512, 'channels':1, 'frame_rate':12.5,
                 'seanet': {'dimension':512, 'channels':1, 'n_filters':64, 'n_residual_layers':1, 'ratios':[6,5,4],
                            'kernel_size':7, 'residual_kernel_size':3, 'last_kernel_size':3, 'dilation_base':2,
                            'pad_mode':'constant', 'compress':2},
                 'transformer': {'d_model':512, 'num_heads':8, 'num_layers':2, 'layer_scale':0.01, 'context':250,
                                 'dim_feedforward':2048, 'input_dimension':512, 'output_dimensions':[512]},
                 'quantizer': {'dimension':32, 'output_dimension':512}},
    }
    (directory / 'config.yaml').write_text(json.dumps(config, indent=2), encoding='utf-8')
    (directory / 'ATTRIBUTION.txt').write_text(
        'Pocket TTS Indonesian by anak10thn; model architecture/base weights by Kyutai; training data by the LEMAS Project.\n'
        'Model license: Creative Commons Attribution 4.0 (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/\n'
        f'Source: https://huggingface.co/{REPO}/tree/{REVISION}\n'
        'Voice prompts: Common Voice 22.0 Indonesian, CC0; common_voice_id_19961910 and common_voice_id_20954552.\n'
        'Local changes: configuration paths changed to offline files; original model weights are unchanged.\n', encoding='utf-8')
    print('Local speech model ready:', directory, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / '.runtime' / 'story-models')
    download(parser.parse_args().root.resolve())
