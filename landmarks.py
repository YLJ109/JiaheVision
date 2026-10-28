"""Lazy MediaPipe face mesh and body landmarks, returning original pixel coordinates.

Create and use an engine from the capture worker only. Call close() when the
worker stops. CPU Tasks are used because MediaPipe's GPU delegate is not
supported on Windows; identity detection continues to use the app's CUDA path.
"""
from importlib.util import find_spec
from pathlib import Path

MODELS = Path(__file__).resolve().parent / 'models'


def availability():
    """Return (ready, explanation) without importing MediaPipe or loading models."""
    if find_spec('mediapipe') is None:
        return False, '未安装 MediaPipe，面部网格与人体关键点不可用'
    missing = [name for name in ('face_landmarker.task', 'pose_landmarker_lite.task')
               if not (MODELS / name).is_file()]
    if missing:
        return False, '缺少关键点模型：' + '、'.join(missing)
    return True, 'MediaPipe CPU · 面部网格 / 人体关键点'


class LandmarkEngine:
    def __init__(self, max_width=960):
        ready, message = availability()
        if not ready:
            raise RuntimeError(message)
        self.status = message
        self.max_width = max(320, int(max_width))
        self.face = self.pose = None
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections
            from mediapipe.tasks.python.vision.pose_landmarker import PoseLandmarksConnections
            self.mp = mp
            base = mp.tasks.BaseOptions
            self.face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=base(model_asset_path=str(MODELS / 'face_landmarker.task')),
                running_mode=vision.RunningMode.IMAGE, num_faces=4,
                min_face_detection_confidence=0.45,
                min_face_presence_confidence=0.45,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False))
            self.pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=base(model_asset_path=str(MODELS / 'pose_landmarker_lite.task')),
                running_mode=vision.RunningMode.IMAGE, num_poses=2,
                min_pose_detection_confidence=0.45,
                min_pose_presence_confidence=0.45,
                output_segmentation_masks=False))
            self.mesh_edges = [(edge.start, edge.end) for edge in FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION]
            self.pose_edges = [(edge.start, edge.end) for edge in PoseLandmarksConnections.POSE_LANDMARKS]
        except Exception as error:
            self.close()
            raise RuntimeError(f'MediaPipe 关键点初始化失败：{error}') from error

    def process(self, image):
        import cv2
        import numpy as np
        if self.face is None or self.pose is None:
            raise RuntimeError('MediaPipe 关键点引擎已关闭')
        if image is None or image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
            raise ValueError('关键点输入必须为非空 BGR 三通道图像')
        height, width = image.shape[:2]
        scale = min(1.0, self.max_width / width)
        frame = cv2.resize(image, (round(width * scale), max(1, round(height * scale)))) if scale < 1 else image
        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        try:
            faces = self.face.detect(mp_image)
            poses = self.pose.detect(mp_image)
        except Exception as error:
            self.status = f'MediaPipe 关键点处理失败：{error}'
            raise RuntimeError(self.status) from error
        return {
            'mesh': [[(point.x * width, point.y * height) for point in face]
                     for face in faces.face_landmarks],
            'mesh_edges': self.mesh_edges,
            'poses': [[(point.x * width, point.y * height, float(point.visibility or 0))
                       for point in pose] for pose in poses.pose_landmarks],
            'pose_edges': self.pose_edges,
        }

    def close(self):
        for name in ('face', 'pose'):
            task = getattr(self, name, None)
            if task is not None:
                task.close()
                setattr(self, name, None)
