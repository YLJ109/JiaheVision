from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
MODELS = {
    'face_detection_yunet.onnx': 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
    'face_recognition_sface.onnx': 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx',
    'yolov8n.onnx': 'https://huggingface.co/unileon-robotics/YOLO8-ONNX/resolve/main/yolov8n.onnx',
}
if __name__ == '__main__':
    folder = ROOT / 'models'
    folder.mkdir(exist_ok=True)
    for name, url in MODELS.items():
        target = folder / name
        if target.exists() and target.stat().st_size > 10000:
            print('Ready:', name, flush=True)
            continue
        print('Downloading:', name, flush=True)
        temp = target.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=90) as source, temp.open('wb') as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        temp.replace(target)
        print('Saved:', name, target.stat().st_size, flush=True)
