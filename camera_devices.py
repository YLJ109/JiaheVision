"""Enumerate DirectShow camera names without opening capture streams."""
import sys

from PyQt6.QtCore import QThread, pyqtSignal


def list_camera_devices():
    if sys.platform != 'win32':
        raise RuntimeError('当前设备枚举支持 Windows DirectShow')
    try:
        import comtypes
    except ImportError as exc:
        raise RuntimeError('缺少摄像头枚举依赖 comtypes，请安装项目依赖') from exc
    comtypes.CoInitialize()
    try:
        try:
            from pygrabber.dshow_graph import FilterGraph
        except ImportError as exc:
            raise RuntimeError('缺少摄像头枚举依赖 pygrabber，请安装项目依赖') from exc
        graph = FilterGraph()
        try:
            names = graph.get_input_devices()
            return [{'index': index, 'name': str(name)} for index, name in enumerate(names)]
        finally:
            # Release COM objects on their owning thread before closing its apartment.
            del graph
    finally:
        comtypes.CoUninitialize()


class CameraScanner(QThread):
    devices_ready = pyqtSignal(list)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.devices_ready.emit(list_camera_devices())
        except Exception as exc:
            self.failed.emit('摄像头设备枚举失败：' + str(exc))
