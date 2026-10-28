"""Geometry-only Qt verification. No detection, telemetry or camera scan threads."""
import bootstrap
import json
import sys
import traceback
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from main import Window, STYLE, Worker
from telemetry import Telemetry
from camera_devices import CameraScanner

def exception_hook(kind, value, tb):
    message = ''.join(traceback.format_exception(kind, value, tb))
    Path(__file__).with_name('output').mkdir(exist_ok=True)
    (Path(__file__).with_name('output') / 'window_exception.txt').write_text(message, encoding='utf-8')
    sys.__excepthook__(kind, value, tb)

sys.excepthook = exception_hook


app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
app.setFont(QFont('Microsoft YaHei UI', 10))
report = {'scope': 'Window geometry only; inference, telemetry and camera scanning threads disabled; no camera enumeration or detection is simulated', 'checks': []}
output = Path(__file__).resolve().parent / 'output'
output.mkdir(exist_ok=True)


def settle():
    app.processEvents()
    QTest.qWait(70)


def mouse(widget, kind, global_point, pressed):
    event = QMouseEvent(kind, QPointF(widget.mapFromGlobal(global_point)), QPointF(global_point),
                        Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton if pressed else Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)
    settle()


def gesture(widget, start, delta):
    target = start + delta
    mouse(widget, QEvent.Type.MouseButtonPress, start, True)
    mouse(widget, QEvent.Type.MouseMove, target, True)
    mouse(widget, QEvent.Type.MouseButtonRelease, target, False)


with patch.object(Worker, 'start'), patch.object(Telemetry, 'start'), patch.object(CameraScanner, 'start'):
    window = Window()
try:
    window.show()
    window.activateWindow()
    settle()
    window.setGeometry(100, 100, 1200, 760)
    settle()
    before = window.pos()
    start = window.topbar.mapToGlobal(QPoint(window.topbar.width() // 2, 30))
    gesture(window.topbar, start, QPoint(50, 25))
    assert window.pos() == before + QPoint(50, 25), (before, window.pos())
    report['checks'].append('Title bar drag')

    cases = [('left', QPoint(5, 380), QPoint(-40, 0), 1240, 760),
             ('right', QPoint(1195, 380), QPoint(40, 0), 1240, 760),
             ('top', QPoint(600, 5), QPoint(0, -30), 1200, 790),
             ('bottom', QPoint(600, 755), QPoint(0, 30), 1200, 790),
             ('top-left', QPoint(5, 5), QPoint(-40, -30), 1240, 790),
             ('top-right', QPoint(1195, 5), QPoint(40, -30), 1240, 790),
             ('bottom-left', QPoint(5, 755), QPoint(-40, 30), 1240, 790),
             ('bottom-right', QPoint(1195, 755), QPoint(40, 30), 1240, 790)]
    for name, local, delta, width, height in cases:
        window.setGeometry(100, 100, 1200, 760)
        settle()
        gesture(window, window.mapToGlobal(local), delta)
        assert (window.width(), window.height()) == (width, height), (name, window.geometry())
        report['checks'].append(name + ' resize')

    window.setGeometry(100, 100, 1200, 760)
    settle()
    gesture(window, window.mapToGlobal(QPoint(1195, 755)), QPoint(-1000, -1000))
    assert window.width() >= window.minimumWidth() and window.height() >= window.minimumHeight(), window.geometry()
    report['checks'].append(f'Minimum resize bounds: actual {window.width()}x{window.height()}, declared {window.minimumWidth()}x{window.minimumHeight()}')

    window.activateWindow()
    window.setFocus()
    settle()
    QTest.keyClick(window, Qt.Key.Key_F11)
    settle()
    assert window.isFullScreen(), 'F11 did not enter fullscreen'
    QTest.keyClick(window, Qt.Key.Key_Escape)
    settle()
    assert not window.isFullScreen(), 'Escape did not exit fullscreen'
    report['checks'].append('F11 and Escape fullscreen')

    for width, height in [(960, 620), (1440, 900)]:
        window.resize(width, height)
        settle()
        report['checks'].append(f'Requested {width}x{height}, actual {window.width()}x{window.height()}')
        canvas = window.canvas
        dock = canvas.dock
        assert canvas.rect().contains(dock.geometry()), (width, canvas.size(), dock.geometry())
        ratio = canvas.width() / (canvas.width() + window.sidebar.width())
        assert .65 < ratio < .85, (width, ratio)
        assert all(dock.rect().contains(button.geometry()) for button in window.dock_buttons)
        assert window.grab().save(str(output / f'verified_window_{width}.png'))
        report['checks'].append(f'{width}x{height} dock containment and {ratio:.3f} canvas ratio')
    report['success'] = True
except Exception as exc:
    report['success'] = False
    report['error'] = str(exc)
    raise
finally:
    window.close()
    (output / 'window_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
