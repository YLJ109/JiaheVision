"""Opt-in frozen-binary smoke test; normal launches never enter this branch."""
import os

if os.environ.get('JIAHE_PACKAGE_SELF_TEST'):
    import json
    import sys
    import traceback
    from pathlib import Path
    report = {}
    exit_code = 0
    try:
        # User runtime hooks precede PyInstaller's Qt runtime hook.
        qt_root = Path(sys._MEIPASS) / 'PyQt6' / 'Qt6'
        os.environ['QT_PLUGIN_PATH'] = str(qt_root / 'plugins')
        qt_dll_directory = os.add_dll_directory(str(qt_root / 'bin'))
        import numpy as np
        import cv2
        import onnxruntime as ort
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtSvg import QSvgRenderer
        from PIL import Image
        import storage
        from vision import Engine
        from landmarks import LandmarkEngine
        from camera_devices import list_camera_devices
        report['providers'] = ort.get_available_providers()
        report['camera_devices'] = list_camera_devices()
        assert 'CUDAExecutionProvider' not in report['providers']
        app = QApplication([])
        store = storage.Store()
        engine = Engine()
        engine.reload(store.students())
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        report['blank_people'] = len(engine.people(frame))
        landmark = LandmarkEngine()
        result = landmark.process(frame)
        report['mesh_edges'] = len(result['mesh_edges'])
        report['pose_edges'] = len(result['pose_edges'])
        landmark.close()
        report['root'] = str(storage.ROOT)
        report['data'] = str(storage.DATA)
        report['students'] = len(store.students())
        report['profiles'] = store.profiles()
        for sid, profile in report['profiles'].items():
            assert Path(profile['photo']).is_file(), profile['photo']
        report['identity_verification'] = []
        for sid, profile in report['profiles'].items():
            image = cv2.imdecode(np.fromfile(profile['photo'], np.uint8), cv2.IMREAD_COLOR)
            faces = engine.faces(image)
            assert len(faces) == 1
            result = engine.identify(engine.embedding(image, faces[0]))
            assert result[0] == sid, (sid, result)
            report['identity_verification'].append(dict(student_id=result[0], name=result[1], score=result[2]))
        icons = list((storage.ROOT / 'assets/icons').glob('*.svg'))
        report['svg_icons'] = len(icons)
        assert icons and all(QSvgRenderer(str(icon)).isValid() for icon in icons)
        assert not store.checkins()
        store.db.close()
        report['ok'] = True
    except BaseException:
        report['ok'] = False
        report['error'] = traceback.format_exc()
        exit_code = 1
    Path(os.environ['JIAHE_PACKAGE_SELF_TEST']).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    sys.exit(exit_code)
