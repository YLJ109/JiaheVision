import bootstrap
import os
import time
import threading
from collections import deque
from pathlib import Path
import cv2
import numpy as np
import onnxruntime as ort
from PyQt6.QtCore import QThread, pyqtSignal
from storage import ROOT, DATA


class BoxTracker:
    """Short-lived visual tracks; IDs are unrelated to enrolled identities."""
    def __init__(self):
        self.tracks = {}
        self.next_id = 1

    def update(self, boxes):
        now = time.monotonic()
        self.tracks = {key: value for key, value in self.tracks.items() if now - value['seen'] < .8}
        available = set(self.tracks)
        results = []
        for box in boxes:
            raw = np.asarray(box, dtype=np.float32)
            best_id, best_score = None, .15
            for key in available:
                prior = self.tracks[key]['box']
                start = np.maximum(raw[:2], prior[:2])
                end = np.minimum(raw[:2] + raw[2:], prior[:2] + prior[2:])
                intersection = float(np.prod(np.maximum(end - start, 0)))
                union = float(np.prod(raw[2:]) + np.prod(prior[2:]) - intersection)
                score = intersection / max(union, 1.)
                if score > best_score:
                    best_id, best_score = key, score
            if best_id is None:
                best_id = self.next_id
                self.next_id += 1
                smooth = raw
            else:
                available.remove(best_id)
                smooth = .7 * raw + .3 * self.tracks[best_id]['box']
            self.tracks[best_id] = {'box': smooth, 'seen': now}
            results.append({'track_id': best_id, 'box': tuple(np.rint(smooth).astype(int))})
        return results


def follow_landmarks(data, anchors, current):
    """Move cached overlays with session boxes between landmark inference frames."""
    output = dict(data)
    for field, category in (('mesh', 'faces'), ('poses', 'people')):
        previous = anchors.get(category, [])
        latest = {track['track_id']: track['box'] for track in current.get(category, [])}
        groups = []
        for points in data.get(field, []):
            visible = [point for point in points if len(point) < 3 or point[2] > .5]
            if not visible or not previous:
                continue
            center = np.mean(np.asarray(visible)[:, :2], axis=0)
            def distance(track):
                x, y, w, h = track['box']
                return ((center[0] - x - w / 2) / max(w, 1))**2 + ((center[1] - y - h / 2) / max(h, 1))**2
            anchor = min(previous, key=distance)
            if anchor['track_id'] not in latest or distance(anchor) > 2:
                continue
            x, y, w, h = anchor['box']
            nx, ny, nw, nh = latest[anchor['track_id']]
            groups.append([(nx + (point[0] - x) * nw / max(w, 1),
                            ny + (point[1] - y) * nh / max(h, 1), *point[2:]) for point in points])
        output[field] = groups
    return output


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        models = ROOT / 'models'
        for filename in ('face_detection_yunet.onnx', 'face_recognition_sface.onnx', 'yolov8n.onnx'):
            if not (models / filename).exists():
                raise RuntimeError('缺少模型：' + filename + '，请先运行 download_models.py')
        self.detector = cv2.FaceDetectorYN.create(str(models / 'face_detection_yunet.onnx'), '', (640, 640), .8, .3, 300)
        self.aligner = cv2.FaceRecognizerSF.create(str(models / 'face_recognition_sface.onnx'), '')
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, max(1, (os.cpu_count() or 2) // 2))
        options.inter_op_num_threads = 1
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        options.add_session_config_entry('session.inter_op.allow_spinning', '0')
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        cv2.setNumThreads(2)
        options.log_severity_level = 3
        self.warning = ''
        providers = ['CPUExecutionProvider']
        self.face = ort.InferenceSession(str(models / 'face_recognition_sface.onnx'), sess_options=options, providers=providers)
        self.person = ort.InferenceSession(str(models / 'yolov8n.onnx'), sess_options=options, providers=providers)
        self.gpu = False
        self.face_input = self.face.get_inputs()[0].name
        self.person_input = self.person.get_inputs()[0].name
        person_shape = self.person.get_inputs()[0].shape
        self.person_height = person_shape[2] if isinstance(person_shape[2], int) else 640
        self.person_width = person_shape[3] if isinstance(person_shape[3], int) else 640
        self.gallery = []
        self.threshold = .45
        # Warm up CPU kernels before accepting a source.
        self.face.run(None, {self.face_input: np.zeros((1, 3, 112, 112), np.float32)})
        self.people(np.zeros((480, 640, 3), np.uint8))

    def reload(self, students):
        with self.lock:
            self.gallery = [(row[0], row[1], np.frombuffer(row[3], np.float32).copy()) for row in students]

    def faces(self, image):
        with self.lock:
            h, w = image.shape[:2]
            scale = min(1., 960 / max(w, h))
            view = cv2.resize(image, (round(w * scale), round(h * scale))) if scale < 1 else image
            self.detector.setInputSize((view.shape[1], view.shape[0]))
            _, faces = self.detector.detect(view)
            if faces is None:
                return []
            # Restore boxes and all five landmarks to the displayed frame coordinates.
            faces[:, :14] /= scale
            return faces

    def embedding(self, image, face):
        with self.lock:
            aligned = self.aligner.alignCrop(image, face)
            # SFace's ONNX graph contains normalization; input is raw RGB 0..255.
            blob = cv2.dnn.blobFromImage(aligned, 1., (112, 112), (0, 0, 0), swapRB=True)
            feature = self.face.run(None, {self.face_input: blob})[0].reshape(-1)
            return feature / max(np.linalg.norm(feature), 1e-8)

    def identify(self, embedding):
        with self.lock:
            if not self.gallery:
                return '', '未知人员', 0.
            scores = sorted([(float(np.dot(embedding, f) / max(np.linalg.norm(f), 1e-8)), sid, name) for sid, name, f in self.gallery], reverse=True)
            score, sid, name = scores[0]
            if score < self.threshold or (len(scores) > 1 and score - scores[1][0] < .06):
                return '', '未知人员', score
            return sid, name, score

    def people(self, image):
        h, w = image.shape[:2]
        height, width = self.person_height, self.person_width
        scale = min(width / w, height / h)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        pad_x, pad_y = (width - nw) // 2, (height - nh) // 2
        canvas = np.full((height, width, 3), 114, np.uint8)
        canvas[pad_y:pad_y+nh, pad_x:pad_x+nw] = cv2.resize(image, (nw, nh))
        blob = cv2.dnn.blobFromImage(canvas, 1/255., (width, height), swapRB=True)
        pred = self.person.run(None, {self.person_input: blob})[0]
        pred = pred[0] if pred.ndim == 3 else pred
        if pred.ndim != 2:
            raise RuntimeError('人体模型输出维度不正确：' + str(pred.shape))
        if pred.shape[0] < pred.shape[1]:
            pred = pred.T
        # Filter all anchors in NumPy; Python iteration over 8,400 rows costs
        # noticeable time on every frame, especially when GPU inference is fast.
        valid = (pred[:, 4] >= .45) & (np.argmax(pred[:, 4:], axis=1) == 0)
        selected = pred[valid]
        if not len(selected):
            return []
        corners = selected[:, :4].copy()
        corners[:, :2] -= corners[:, 2:] / 2
        corners[:, 2:] += corners[:, :2]
        corners[:, [0, 2]] = np.clip((corners[:, [0, 2]] - pad_x) / scale, 0, w)
        corners[:, [1, 3]] = np.clip((corners[:, [1, 3]] - pad_y) / scale, 0, h)
        corners[:, 2:] -= corners[:, :2]
        nonempty = (corners[:, 2] >= 1) & (corners[:, 3] >= 1)
        boxes = corners[nonempty].astype(np.int32).tolist()
        scores = selected[nonempty, 4].tolist()
        if not boxes:
            return []
        keep = cv2.dnn.NMSBoxes(boxes, scores, .45, .45)
        return [boxes[int(i)] for i in np.asarray(keep).flatten()] if len(keep) else []


class CapturePump(threading.Thread):
    """Own capture on one thread; overwrite a single slot instead of queueing frames."""
    def __init__(self, source, preview, status):
        super().__init__(daemon=True, name='latest-frame-capture')
        self.source, self.preview, self.status = source, preview, status
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.paused = False
        self.mirror_camera = True
        self.latest = None
        self.sequence = 0
        self.ended = False
        self.source_fps = 0.
        self.preview_fps = 0.
        self.last_read = time.perf_counter()
        self.preview_times = deque(maxlen=60)

    def take(self, after):
        with self.lock:
            return self.latest if self.latest is not None and self.latest[0] > after else None

    def stop(self):
        self.stop_event.set()
        self.join(timeout=2)
        if self.is_alive():
            self.status('视频源驱动停止响应，正在等待读取线程安全退出')

    def wait_seconds(self, seconds):
        # Python's sleep uses the high-resolution Windows timer; Event.wait
        # can round a 33 ms frame deadline up to roughly 47 ms on this machine.
        deadline = time.perf_counter() + max(0., seconds)
        while not self.stop_event.is_set():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(.02, remaining))

    def run(self):
        capture = None
        camera = isinstance(self.source, int)
        try:
            capture = cv2.VideoCapture(self.source, cv2.CAP_DSHOW) if camera else cv2.VideoCapture(self.source)
            if not capture.isOpened():
                self.status('无法打开摄像头 / 视频文件')
                return
            if camera:
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            rate = capture.get(cv2.CAP_PROP_FPS)
            self.source_fps = float(rate) if np.isfinite(rate) and rate > 0 else 0.
            deadline = time.perf_counter()
            last_preview = 0.
            while not self.stop_event.is_set():
                if self.paused and not camera:
                    self.stop_event.wait(.02)
                    deadline = time.perf_counter()
                    continue
                if not camera:
                    self.wait_seconds(max(0., deadline - time.perf_counter()))
                    if self.stop_event.is_set():
                        break
                    deadline = max(deadline + 1 / (self.source_fps or 25), time.perf_counter())
                ok, image = capture.read()
                if self.stop_event.is_set():
                    break
                now = time.perf_counter()
                self.last_read = now
                if not ok:
                    self.status('摄像头读取失败 / 已断开' if camera else '视频播放结束')
                    break
                if self.paused:
                    continue
                h, w = image.shape[:2]
                if w > 1280:
                    image = cv2.resize(image, (1280, round(h * 1280 / w)))
                if camera and self.mirror_camera:
                    image = cv2.flip(image, 1)
                with self.lock:
                    self.sequence += 1
                    self.latest = (self.sequence, now, image)
                # At <=30 Hz, wait for the preview deadline rather than dropping
                # alternate frames because of small camera/file timing jitter.
                preview_due = now - last_preview >= 1 / 30
                if 0 < self.source_fps <= 30 and not preview_due:
                    self.wait_seconds(1 / 30 - (now - last_preview))
                    now = time.perf_counter()
                    preview_due = True
                if not self.paused and not self.stop_event.is_set() and preview_due:
                    if self.preview_times and now - self.preview_times[-1] > .5:
                        self.preview_times.clear()
                    self.preview(image)
                    last_preview = now
                    self.preview_times.append(now)
                    if len(self.preview_times) > 1:
                        self.preview_fps = (len(self.preview_times) - 1) / (now - self.preview_times[0])
        except Exception as exc:
            self.status('视频源异常：' + str(exc))
        finally:
            if capture is not None:
                capture.release()
            self.ended = True


class Worker(QThread):
    frame_ready = pyqtSignal(object, object)
    preview_ready = pyqtSignal(object)
    state = pyqtSignal(str)
    failed = pyqtSignal(str)
    engine_ready = pyqtSignal(object)

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.engine = None
        self.source = None
        self.active = False
        self.stopping = False
        self.command_lock = threading.Lock()
        self.pending_source = None
        self.has_command = False
        self.unique = set()
        self.last_frame = None
        self.source_name = ''
        self.camera_names = {}
        self.image_mode = False
        self.ended = False
        self.face_tracker = BoxTracker()
        self.person_tracker = BoxTracker()
        self.landmarks_enabled = True
        self.landmark_engine = None
        self.landmark_data = {}
        self.landmark_anchors = {}
        self.frame_number = 0
        self.output_times = deque(maxlen=120)
        self.source_fps = 0.
        self.capture_pump = None
        self.mirror_camera = True
        self.adaptive_target_fps = 12.
        self.inference_ema = 1 / 12
        self.landmark_interval = 3

    def open_source(self, source):
        with self.command_lock:
            self.pending_source = source
            self.has_command = True
        self.active = True

    def run(self):
        still = None
        last_sequence = 0
        next_inference = 0.
        last_adaptation = time.perf_counter()
        stall_reported = False
        try:
            self.state.emit('正在初始化视觉引擎…')
            self.engine = Engine()
            self.engine.reload(self.store.students())
            self.engine_ready.emit(self.engine)
            try:
                self.state.emit('正在准备面部网格和骨架…')
                from landmarks import LandmarkEngine
                self.landmark_engine = LandmarkEngine()
                self.state.emit('面部网格和骨架就绪')
            except Exception as exc:
                self.state.emit('轮廓 / 关节点暂不可用：' + str(exc))
            self.state.emit('视觉引擎就绪 · 等待视频源')
            while not self.stopping:
                with self.command_lock:
                    command = self.has_command
                    source = self.pending_source
                    self.has_command = False
                if command:
                    self.face_tracker.tracks.clear()
                    self.person_tracker.tracks.clear()
                    self.landmark_data = {}
                    self.landmark_anchors = {}
                    self.frame_number = 0
                    self.output_times.clear()
                    self.source_fps = 0.
                    self.adaptive_target_fps = 12.
                    self.inference_ema = 1 / 12
                    self.landmark_interval = 3
                    last_adaptation = time.perf_counter()
                    self.ended = False
                    if self.capture_pump is not None:
                        self.capture_pump.stop()
                        self.capture_pump = None
                    last_sequence = 0
                    next_inference = 0.
                    stall_reported = False
                    still = None
                    self.source = source
                    if isinstance(source, int):
                        device_name = self.camera_names.get(source, '')
                        self.source_name = f'摄像头 {source + 1:02d}' + (f' · {device_name}' if device_name else '')
                    else:
                        self.source_name = Path(source).name
                    self.image_mode = isinstance(source, str) and Path(source).suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
                    if self.image_mode:
                        still = cv2.imdecode(np.fromfile(source, np.uint8), cv2.IMREAD_COLOR)
                        if still is None:
                            self.failed.emit('图片读取失败')
                            self.active = False
                    else:
                        self.capture_pump = CapturePump(source, self.preview_ready.emit, self.state.emit)
                        self.capture_pump.mirror_camera = self.mirror_camera
                        self.capture_pump.start()
                pump = self.capture_pump
                if pump is not None:
                    pump.paused = not self.active
                    pump.mirror_camera = self.mirror_camera
                if not self.active or (pump is None and still is None):
                    self.msleep(15)
                    continue
                started = time.perf_counter()
                if still is not None:
                    image = still.copy()
                    captured_at = started
                else:
                    sample = pump.take(last_sequence)
                    if sample is None:
                        if pump.ended:
                            self.active = False
                            self.ended = True
                        elif started - pump.last_read > 3 and not stall_reported:
                            self.state.emit('视频源读取超过 3 秒未响应，请检查摄像头连接')
                            stall_reported = True
                        self.msleep(5)
                        continue
                    if started < next_inference:
                        self.msleep(min(15, max(1, int((next_inference - started)*1000))))
                        continue
                    last_sequence, captured_at, image = sample
                    self.source_fps = pump.source_fps
                    stall_reported = False
                h, w = image.shape[:2]
                if w > 1280:
                    image = cv2.resize(image, (1280, round(h * 1280 / w)))
                self.last_frame = image.copy()
                inference_started = time.perf_counter()
                people = self.engine.people(image)
                faces = self.engine.faces(image)
                person_tracks = self.person_tracker.update(people)
                face_tracks = self.face_tracker.update([face[:4] for face in faces])
                current_tracks = {'faces': face_tracks, 'people': person_tracks}
                current_landmarks = {}
                if self.landmarks_enabled and self.landmark_engine is not None and self.frame_number % self.landmark_interval == 0:
                    try:
                        self.landmark_data = self.landmark_engine.process(image)
                        self.landmark_anchors = current_tracks
                        current_landmarks = self.landmark_data
                    except Exception as exc:
                        self.landmark_data = {}
                        self.landmarks_enabled = False
                        self.state.emit('轮廓 / 关节点已暂停：' + str(exc))
                elif self.landmarks_enabled and self.landmark_data:
                    current_landmarks = follow_landmarks(self.landmark_data, self.landmark_anchors, current_tracks)
                self.frame_number += 1
                inference_seconds = time.perf_counter() - inference_started
                detected = []
                for face, track in zip(faces, face_tracks):
                    x, y, fw, fh = map(int, face[:4])
                    if fw < 28 or fh < 28:
                        continue
                    face_started = time.perf_counter()
                    embedding = self.engine.embedding(image, face)
                    sid, name, score = self.engine.identify(embedding)
                    inference_seconds += time.perf_counter() - face_started
                    item = {'box': (x, y, fw, fh), 'landmarks': face[4:14].reshape(5, 2).tolist(), 'sid': sid, 'name': name, 'score': score, 'photo': ''}
                    item['box'] = track['box']
                    item['track_id'] = track['track_id']
                    if sid:
                        self.unique.add(sid)
                    detected.append(item)
                finished = time.perf_counter()
                elapsed = finished - started
                self.inference_ema = .85 * self.inference_ema + .15 * elapsed
                if finished - last_adaptation >= 2:
                    self.adaptive_target_fps = float(np.clip(.8 / max(self.inference_ema, .001), 4, 20))
                    self.landmark_interval = int(np.clip(round(self.inference_ema / .025), 3, 6))
                    last_adaptation = finished
                next_inference = started + 1 / self.adaptive_target_fps
                if self.output_times and finished - self.output_times[-1] > 2:
                    self.output_times.clear()
                self.output_times.append(finished)
                while len(self.output_times) > 2 and finished - self.output_times[0] > 2:
                    self.output_times.popleft()
                detect_fps = ((len(self.output_times) - 1) / (finished - self.output_times[0])) if len(self.output_times) > 1 else 0.
                stats = {'people': people, 'faces': detected, 'unique': len(self.unique), 'fps': 1/max(elapsed, .001), 'latency': elapsed*1000, 'source': self.source_name, 'gpu': self.engine.gpu}
                stats.update(detect_fps=detect_fps, inference_ms=inference_seconds*1000,
                             source_fps=self.source_fps, frame_number=self.frame_number)
                stats.update(adaptive_target_fps=self.adaptive_target_fps,
                             preview_fps=pump.preview_fps if pump is not None else 0.,
                             quality_label=f'CPU 自适应 · 关键点每 {self.landmark_interval} 帧',
                             frame_age_ms=max(0., (finished - captured_at)*1000))
                stats['people'] = [track['box'] for track in person_tracks]
                stats['person_tracks'] = person_tracks
                if self.landmarks_enabled:
                    stats.update(current_landmarks)
                self.frame_ready.emit(image, stats)
                if still is not None:
                    self.active = False
                    self.ended = True
                    self.state.emit('图片分析完成')
        except Exception as exc:
            import traceback
            (DATA / 'logs').mkdir(parents=True, exist_ok=True)
            (DATA / 'logs' / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
            self.failed.emit(str(exc))
        finally:
            if self.capture_pump is not None:
                self.capture_pump.stop()
            if self.landmark_engine is not None and hasattr(self.landmark_engine, 'close'):
                self.landmark_engine.close()
