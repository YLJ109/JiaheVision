"""Measured Windows CPU/RAM and optional NVIDIA GPU telemetry."""
import ctypes
from ctypes import wintypes
import math
import subprocess
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal


class Telemetry(QThread):
    updated = pyqtSignal(dict)
    _cpu_previous = None
    _cpu_lock = threading.Lock()

    @staticmethod
    def system_metrics():
        result = {'cpu_available': False, 'cpu_util': None, 'ram_used': None,
                  'ram_total': None, 'process_ram': None, 'cpu_error': ''}
        try:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            get_times = kernel.GetSystemTimes
            get_times.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
            get_times.restype = wintypes.BOOL
            idle, system, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            if not get_times(ctypes.byref(idle), ctypes.byref(system), ctypes.byref(user)):
                raise ctypes.WinError(ctypes.get_last_error())
            def ticks(value):
                return (value.dwHighDateTime << 32) | value.dwLowDateTime
            current = (ticks(idle), ticks(system) + ticks(user))
            with Telemetry._cpu_lock:
                previous = Telemetry._cpu_previous
                Telemetry._cpu_previous = current
            if previous is not None:
                total = current[1] - previous[1]
                if total > 0:
                    result['cpu_util'] = max(0., min(100., 100. * (1 - (current[0] - previous[0]) / total)))

            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
                    (name, ctypes.c_ulonglong) for name in
                    ('total_phys', 'avail_phys', 'total_page', 'avail_page', 'total_virtual', 'avail_virtual', 'extended')]
            memory = MemoryStatus()
            memory.length = ctypes.sizeof(memory)
            memory_status = kernel.GlobalMemoryStatusEx
            memory_status.argtypes = [ctypes.POINTER(MemoryStatus)]
            memory_status.restype = wintypes.BOOL
            if not memory_status(ctypes.byref(memory)):
                raise ctypes.WinError(ctypes.get_last_error())
            result['ram_total'] = memory.total_phys / 1024**2
            result['ram_used'] = (memory.total_phys - memory.avail_phys) / 1024**2
            result['cpu_available'] = True
            try:
                class ProcessMemory(ctypes.Structure):
                    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                        (name, ctypes.c_size_t) for name in
                        ('peak_working_set', 'working_set', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
                counters = ProcessMemory()
                counters.cb = ctypes.sizeof(counters)
                kernel.GetCurrentProcess.restype = wintypes.HANDLE
                get_memory = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
                get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
                get_memory.restype = wintypes.BOOL
                if get_memory(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                    result['process_ram'] = counters.working_set / 1024**2
            except (OSError, AttributeError):
                pass
        except (OSError, AttributeError) as exc:
            result['cpu_error'] = str(exc)
        return result

    @staticmethod
    def poll():
        result = {'available': False, 'error': '', 'util': None,
                  'used': None, 'total': None, 'temp': None, 'power': None}
        result.update(Telemetry.system_metrics())
        try:
            process = subprocess.run(
                ['nvidia-smi', '--id=0',
                 '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=2,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            if process.returncode:
                raise RuntimeError(process.stderr.strip() or f'nvidia-smi exited {process.returncode}')
            lines = process.stdout.strip().splitlines()
            if not lines:
                raise ValueError('nvidia-smi returned no GPU measurements')
            values = [part.strip() for part in lines[0].split(',')]
            if len(values) != 5:
                raise ValueError('Unexpected nvidia-smi measurement format')
            for key, value in zip(('util', 'used', 'total', 'temp', 'power'), values):
                try:
                    number = float(value)
                    if not math.isfinite(number):
                        continue
                    result[key] = number
                except ValueError:
                    pass  # Unsupported sensors remain None; never replace with zero.
            result['available'] = any(result[key] is not None for key in ('util', 'used', 'total', 'temp', 'power'))
            if not result['available']:
                result['error'] = 'GPU measurements are unavailable'
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
            result['error'] = str(exc)
        return result

    def run(self):
        while not self.isInterruptionRequested():
            started = time.monotonic()
            self.updated.emit(self.poll())
            # Small waits keep interruption latency bounded without a busy loop.
            while time.monotonic() - started < 1:
                if self.isInterruptionRequested():
                    return
                self.msleep(min(100, max(1, int((1 - (time.monotonic()-started))*1000))))
