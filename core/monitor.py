"""
core/monitor.py
Watches for a running RSDragonwilds.exe process and tracks uptime.
"""

import re
import psutil
import threading
import time
from datetime import datetime
from pathlib import Path

SERVER_EXE = "RSDragonwildsServer.exe"
LOG_FILE = "RSDragonwilds.log"
JOIN_RE = re.compile(r"Join succeeded:\s*(.+)")
LEAVE_RE = re.compile(r"Player Removed from session \[[^\]]+\]-\[(.+)\]")


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
        self.player_count = 0
        self.players: set[str] = set()
        self._log_path: Path | None = None
        self._log_offset = 0

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
                        self._reset_player_tracking()
                    elif self.exe_path != proc.info.get("exe", ""):
                        self.exe_path = proc.info.get("exe", "")
                        self._reset_player_tracking()
                    self.is_online = True
                    self.pid       = proc.info["pid"]
                    self._update_player_count()
                    return
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Not found
        self.is_online  = False
        self.pid        = None
        self.start_time = None
        self.exe_path   = None
        self.player_count = 0
        self.players.clear()
        self._log_path = None
        self._log_offset = 0

    def _reset_player_tracking(self):
        self.player_count = 0
        self.players.clear()
        self._log_path = None
        self._log_offset = 0

    def _candidate_log_paths(self) -> list[Path]:
        if not self.exe_path:
            return []
        base = Path(self.exe_path).parent
        return [
            base / "RSDragonwilds" / "Saved" / "Logs" / LOG_FILE,
            base / "Saved" / "Logs" / LOG_FILE,
        ]

    def _update_player_count(self):
        if not self._log_path:
            for candidate in self._candidate_log_paths():
                if candidate.exists():
                    self._log_path = candidate
                    break

        if not self._log_path or not self._log_path.exists():
            self.player_count = len(self.players)
            return

        try:
            size = self._log_path.stat().st_size
            if size < self._log_offset:
                self._log_offset = 0
                self.players.clear()

            with self._log_path.open("r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(self._log_offset)
                for line in fh:
                    self._process_log_line(line.strip())
                self._log_offset = fh.tell()
        except OSError:
            return

        self.player_count = len(self.players)

    def _process_log_line(self, line: str):
        joined = JOIN_RE.search(line)
        if joined:
            self.players.add(joined.group(1).strip())
            return

        left = LEAVE_RE.search(line)
        if left:
            self.players.discard(left.group(1).strip())

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
