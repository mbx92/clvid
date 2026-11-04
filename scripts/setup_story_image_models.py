"""Download pinned local image/translation weights; inference itself stays offline."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services' / 'backend'))
from app.story.local_images import (MODEL_FILES, MODEL_ID, MODEL_REVISION,
                                     TRANSLATION_FILES, TRANSLATION_ID, TRANSLATION_REVISION)


def checksum(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def download_model(root, repo, revision, names):
    url = f'https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true'
    with urllib.request.urlopen(url, timeout=60) as response:
        tree = {row['path']: row for row in json.load(response) if row['type'] == 'file'}
    root.mkdir(parents=True, exist_ok=True)
    def download(name):
        row = tree[name]
        expected = row.get('lfs', {}).get('oid')
        final = root / name
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.is_file() and final.stat().st_size == row['size'] and (not expected or checksum(final) == expected):
            return name, 'cached'
        temporary = final.with_name(final.name + '.partial')
        try:
            with urllib.request.urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{name}', timeout=120) as response, temporary.open('wb') as handle:
                while block := response.read(1024 * 1024):
                    handle.write(block)
            if temporary.stat().st_size != row['size'] or expected and checksum(temporary) != expected:
                raise ValueError(f'Checksum/size mismatch: {name}')
            temporary.replace(final)
        finally:
            temporary.unlink(missing_ok=True)
        return name, 'downloaded'
    with ThreadPoolExecutor(max_workers=2) as pool:
        for name, state in pool.map(download, [*names, 'README.md']):
            print(f'{repo}: {name} {state}', flush=True)
    (root / 'MODEL_SOURCE.json').write_text(json.dumps({'repository':repo,'revision':revision,
        'files':{name:{'bytes':tree[name]['size'],'sha256':tree[name].get('lfs',{}).get('oid')} for name in names}}, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.runtime/story-models'))
    args = parser.parse_args()
    download_model(args.root / 'images/sd15', MODEL_ID, MODEL_REVISION, MODEL_FILES)
    download_model(args.root / 'translation/id-en', TRANSLATION_ID, TRANSLATION_REVISION, TRANSLATION_FILES)
    license_path = args.root / 'images/sd15/LICENSE.txt'
    with urllib.request.urlopen('https://raw.githubusercontent.com/CompVis/stable-diffusion/21f890f9da3cfbeaba8e2ac3c425ee9e998d5229/LICENSE', timeout=30) as response:
        license_path.write_bytes(response.read())


if __name__ == '__main__':
    main()
