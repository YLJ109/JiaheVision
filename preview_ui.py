import bootstrap
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from main import Window, STYLE
from vision import Worker
from storage import ROOT

# UI-only preview while GPU runtime is being installed; no simulated detections.
Worker.start = lambda self: None
app = QApplication(sys.argv)
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
app.setFont(QFont('Microsoft YaHei UI',10))
window = Window()
window.status.setText('界面预览 · GPU 运行库安装中，检测尚未启动')
window.device.setText('○  GPU 运行库准备中')
window.show()
def capture():
    (ROOT / 'output').mkdir(exist_ok=True)
    window.grab().save(str(ROOT / 'output/interface.png'))
QTimer.singleShot(1000,capture)
sys.exit(app.exec())
