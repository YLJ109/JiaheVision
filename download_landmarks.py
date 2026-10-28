"""Download the official MediaPipe task bundles used by landmarks.py."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
import zipfile

MODELS = Path(__file__).resolve().parent / 'models'
URLS = {
    'face_landmarker.task': 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task',
    'pose_landmarker_lite.task': 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task',
}


def download(item):
    name, url = item
    MODELS.mkdir(exist_ok=True)
    target = MODELS / name
    if target.exists() and zipfile.is_zipfile(target):
        print('Ready:', name, flush=True)
        return
    temporary = target.with_suffix('.task.part')
    print('Downloading:', name, flush=True)
    with urllib.request.urlopen(url, timeout=90) as source, temporary.open('wb') as output:
        while chunk := source.read(1024 * 1024):
            output.write(chunk)
    if not zipfile.is_zipfile(temporary):
        raise RuntimeError(f'Invalid MediaPipe model bundle: {name}')
    temporary.replace(target)
    print('Saved:', name, target.stat().st_size, flush=True)


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(download, URLS.items()))
