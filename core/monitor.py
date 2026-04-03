"""
core/monitor.py
Watches for a running RSDragonwilds.exe process and tracks uptime.
"""

import psutil
import threading
import time
from datetime import datetime
from pathlib import Path

SERVER_EXE = "RSDragonwildsServer.exe"


class ServerMonitor:
    """Polls for a running server process every N seconds."""

    def __init__(self, poll_interval: int = 3):
        self.poll_interval = poll_interval
        self._running = False
        self._thread: object = None

        # State
        self.is_online = False
        self.pid: object = None
        self.start_time: object = None
        self.exe_path: object = None

        # Callbacks
        self.on_status_change = None   # callable(is_online: bool)
        self.on_tick = None            # callable() -- fires every poll cycle

    # ------------------------------------------------------------------
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    def _loop(self):
        while self._running:
            was_online = self.is_online
            self._poll()
            if self.is_online != was_online and self.on_status_change:
                self.on_status_change(self.is_online)
            if self.on_tick:
                self.on_tick()
            time.sleep(self.poll_interval)

    def _poll(self):
        for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
            try:
                if proc.info["name"] and SERVER_EXE.lower() in proc.info["name"].lower():
                    if not self.is_online:
                        self.start_time = datetime.fromtimestamp(proc.info["create_time"])
                        self.exe_path   = proc.info.get("exe", "")
                    self.is_online = True
                    self.pid       = proc.info["pid"]
                    return
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Not found
        self.is_online  = False
        self.pid        = None
        self.start_time = None
        self.exe_path   = None

    # ------------------------------------------------------------------
    @property
    def uptime_str(self) -> str:
        if not self.is_online or self.start_time is None:
            return "--"
        delta = datetime.now() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def kill(self) -> bool:
        """Terminate the server process. Returns True on success."""
        if self.pid is None:
            return False
        try:
            proc = psutil.Process(self.pid)
            proc.terminate()
            proc.wait(timeout=5)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
            return False
