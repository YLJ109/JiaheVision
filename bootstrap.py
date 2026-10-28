import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, 'frozen', False))
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
if not FROZEN and sys.prefix == sys.base_prefix:
    sys.path.insert(0, str(ROOT / '.packages'))
os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
# MediaPipe's optional documentation helper otherwise imports an unrelated,
# globally installed TensorFlow package and slows a small desktop app's startup.
sys.modules.setdefault('tensorflow', None)
