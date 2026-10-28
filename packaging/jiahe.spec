from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parent
datas = [(str(path), 'models') for path in (root / 'models').glob('*')
         if path.suffix in {'.onnx', '.task'}]
datas += [(str(root / 'assets' / name), 'assets') for name in ('logo.png', 'logo.ico')]
datas += [(str(path), 'assets/icons') for path in (root / 'assets' / 'icons').glob('*.svg')]
if (root / 'packaging' / 'seed' / 'jiahe.db').exists():
    datas += [(str(root / 'packaging' / 'seed' / 'jiahe.db'), 'seed')]
    datas += [(str(path), 'seed/faces') for path in (root / 'packaging' / 'seed' / 'faces').glob('*.jpg')]
datas += collect_data_files('mediapipe')
hidden = collect_submodules('mediapipe', filter=lambda name: '.test' not in name)
hidden += ['PyQt6.QtSvg', 'PyQt6.QtSvgWidgets']
hidden += ['pygrabber.dshow_graph']
hidden += collect_submodules('comtypes', filter=lambda name: not name.startswith('comtypes.test'))
binaries = collect_dynamic_libs('mediapipe') + collect_dynamic_libs('onnxruntime')
a = Analysis([str(root / 'main.py')], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hidden,
             runtime_hooks=[str(root / 'packaging' / 'self_test_hook.py')],
             excludes=['tensorflow', 'torch', 'torchvision', 'torchaudio', 'jax',
                       'jaxlib', 'keras', 'matplotlib', 'nvidia', 'scipy', 'pandas',
                       'IPython', 'notebook', 'pytest', 'tkinter', 'PyQt6.QtWebEngineCore',
                       'PyQt6.QtWebEngineWidgets', 'PyQt6.QtQml', 'PyQt6.QtQuick'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='JiaheVision',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, icon=str(root / 'assets' / 'logo.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='JiaheVision')
