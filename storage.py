import sqlite3
import csv
import json
import threading
from datetime import datetime
from pathlib import Path
import numpy as np
import bootstrap
import os
import shutil

ROOT = bootstrap.ROOT
DATA = (Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'JiaHeVision' / 'data') if bootstrap.FROZEN else ROOT / 'data'
DATA.mkdir(exist_ok=True, parents=True)
(DATA / 'faces').mkdir(exist_ok=True)
_seed = ROOT / 'seed'
if bootstrap.FROZEN and not (DATA / 'jiahe.db').exists() and (_seed / 'jiahe.db').exists():
    shutil.copy2(_seed / 'jiahe.db', DATA / 'jiahe.db')
    for photo in (_seed / 'faces').glob('*.jpg'):
        shutil.copy2(photo, DATA / 'faces' / photo.name)


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(DATA / 'jiahe.db', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY, name TEXT NOT NULL, class_name TEXT,
                embedding BLOB NOT NULL, photo TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, student_id TEXT, name TEXT NOT NULL,
                score REAL, source TEXT, photo TEXT, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_time ON events(created_at);
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
                source TEXT, screenshot TEXT, people_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS checkins_time ON checkins(timestamp);
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(students)')}
        for column, sql_type in (
            ('age', 'INTEGER'), ('gender', 'TEXT'), ('height_cm', 'REAL'),
            ('weight_jin', 'REAL'), ('personality', 'TEXT'), ('appearance_note', 'TEXT'),
        ):
            if column not in columns:
                self.db.execute(f'ALTER TABLE students ADD COLUMN {column} {sql_type}')
        self.db.commit()
        if bootstrap.FROZEN:
            for sid,photo in self.db.execute('SELECT student_id,photo FROM students').fetchall():
                if photo and not Path(photo).is_absolute():
                    self.db.execute('UPDATE students SET photo=? WHERE student_id=?',(str(DATA / photo),sid))
            self.db.commit()

    def students(self):
        with self.lock:
            return self.db.execute('SELECT student_id,name,class_name,embedding,photo FROM students ORDER BY created_at DESC').fetchall()

    def enroll(self, sid, name, class_name, embedding, photo):
        with self.lock:
            self.db.execute('INSERT INTO students(student_id,name,class_name,embedding,photo,created_at) VALUES(?,?,?,?,?,?)',
                            (sid, name, class_name, np.asarray(embedding, np.float32).tobytes(), photo, datetime.now().isoformat(timespec='seconds')))
            self.db.commit()

    def profiles(self):
        """Return profile dictionaries keyed by student ID, without embeddings."""
        with self.lock:
            cursor = self.db.execute('SELECT student_id,name,class_name,photo,age,gender,height_cm,weight_jin,personality,appearance_note FROM students ORDER BY created_at DESC')
            columns = [column[0] for column in cursor.description]
            return {row[0]: dict(zip(columns, row)) for row in cursor.fetchall()}

    def profile(self, sid):
        """Return one profile dictionary, or None for an unknown student ID."""
        with self.lock:
            cursor = self.db.execute('SELECT student_id,name,class_name,photo,age,gender,height_cm,weight_jin,personality,appearance_note FROM students WHERE student_id=?', (sid,))
            row = cursor.fetchone()
            return dict(zip((column[0] for column in cursor.description), row)) if row else None

    def update_profile(self, sid, **fields):
        """Update supplied profile fields; raise for unknown fields or students."""
        allowed = {'age', 'gender', 'height_cm', 'weight_jin', 'personality', 'appearance_note'}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError('Unknown profile fields: ' + ', '.join(sorted(unknown)))
        with self.lock:
            if not fields:
                if self.profile(sid) is None:
                    raise KeyError(sid)
                return
            assignments = ', '.join(f'{column}=?' for column in fields)
            cursor = self.db.execute(f'UPDATE students SET {assignments} WHERE student_id=?', (*fields.values(), sid))
            if cursor.rowcount != 1:
                raise KeyError(sid)
            self.db.commit()

    def event(self, sid, name, score, source, photo):
        now = datetime.now().isoformat(timespec='seconds')
        with self.lock:
            self.db.execute('INSERT INTO events(student_id,name,score,source,photo,created_at) VALUES(?,?,?,?,?,?)', (sid, name, float(score), source, photo, now))
            self.db.commit()
        return now

    def events(self, search=''):
        with self.lock:
            q = '%' + search + '%'
            return self.db.execute('SELECT created_at,name,student_id,score,source,photo FROM events WHERE name LIKE ? OR student_id LIKE ? ORDER BY id DESC LIMIT 1000', (q, q)).fetchall()

    def checkin(self, source, screenshot, people):
        """Save one explicit check-in and its immutable recognized-person snapshot."""
        if not isinstance(people, list) or any(not isinstance(person, dict) for person in people):
            raise ValueError('people must be a list of dictionaries')
        payload = json.dumps(people, ensure_ascii=False, allow_nan=False)
        now = datetime.now().isoformat(timespec='seconds')
        with self.lock:
            cursor = self.db.execute(
                'INSERT INTO checkins(timestamp,source,screenshot,people_json) VALUES(?,?,?,?)',
                (now, str(source), str(screenshot), payload))
            self.db.commit()
            return cursor.lastrowid

    def checkins(self, search=''):
        """Return latest explicit check-ins, including decoded person snapshots."""
        with self.lock:
            query = '%' + str(search) + '%'
            rows = self.db.execute(
                'SELECT id,timestamp,source,screenshot,people_json FROM checkins '
                'WHERE people_json LIKE ? OR source LIKE ? OR timestamp LIKE ? '
                'ORDER BY id DESC LIMIT 1000', (query, query, query)).fetchall()
        return [dict(id=row[0], created_at=row[1], source=row[2], screenshot=row[3],
                     people=json.loads(row[4])) for row in rows]

    def export_checkins(self, path):
        """Export all explicit check-ins as one CSV row per detected person."""
        with self.lock:
            rows = self.db.execute(
                'SELECT id,timestamp,source,screenshot,people_json FROM checkins ORDER BY id DESC').fetchall()
        with open(path, 'w', encoding='utf-8-sig', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(['打卡ID', '时间', '姓名', '学号', '年龄', '性别', '身高(cm)',
                             '体重(斤)', '性格', '备注', '相似度', '视频源', '截图路径'])
            for checkin_id, timestamp, source, screenshot, payload in rows:
                for person in json.loads(payload) or [{'name': '未检测到人员'}]:
                    profile = person.get('profile') or {}
                    if not isinstance(profile, dict):
                        profile = {}
                    merged = {**profile, **person}
                    row = [checkin_id, timestamp, merged.get('name', ''),
                           merged.get('sid') or merged.get('student_id', ''),
                           merged.get('age', ''), merged.get('gender', ''),
                           merged.get('height_cm', ''), merged.get('weight_jin', ''),
                           merged.get('personality', ''), merged.get('appearance_note', ''),
                           merged.get('score', ''), source, screenshot]
                    writer.writerow(["'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@'))
                                     else value for value in row])

    def export(self, path):
        with self.lock:
            rows = self.db.execute('SELECT created_at,name,student_id,score,source FROM events ORDER BY id DESC').fetchall()
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['时间', '姓名', '学号', '相似度', '视频源'])
            # Prevent spreadsheet formulas from executing in exported identity fields.
            for row in rows:
                writer.writerow(["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for v in row])
