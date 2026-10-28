"""Keep MediaPipe's unused 3D plotting dependency lazy in this build venv only."""
from pathlib import Path
import sys

build_root = Path(sys.prefix).resolve()
expected = Path(__file__).resolve().parent.parent / '.buildenv'
if build_root != expected:
    raise RuntimeError('Run this helper only with the project .buildenv Python')
target = build_root / 'Lib/site-packages/mediapipe/tasks/python/vision/drawing_utils.py'
source = target.read_text(encoding='utf-8')
if '\nimport matplotlib.pyplot as plt\n' in source:
    source = source.replace('\nimport matplotlib.pyplot as plt\n', '\n')
    source = source.replace('  plt.figure(figsize=(10, 10))',
                            '  import matplotlib.pyplot as plt\n  plt.figure(figsize=(10, 10))')
    target.write_text(source, encoding='utf-8')
print('MediaPipe 3D plotting import is lazy; face/pose inference is unchanged.')
