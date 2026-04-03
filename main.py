"""
DragonwildsManager - main.py
A full desktop application for managing a RuneScape: Dragonwilds dedicated server.

Run:  python main.py
Build: python build.py   (produces dist/DragonwildsManager.exe)

Requirements:
  pip install psutil pyinstaller
"""

import ctypes
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Make relative imports work whether run directly or as a built exe
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

sys.path.insert(0, str(BASE_DIR))

from core import installer, monitor, settings

# ═══════════════════════════════════════════════════════════════════════════════
#  PALETTE & FONTS
# ═══════════════════════════════════════════════════════════════════════════════

P = {
    "bg":        "#0E0C0A",
    "panel":     "#181410",
    "panel2":    "#201A12",
    "accent":    "#C49638",
    "accent2":   "#8C6A1E",
    "text":      "#E6DCC8",
    "subtext":   "#A08C6E",
    "input_bg":  "#2A2018",
    "success":   "#50C864",
    "error":     "#DC503C",
    "warn":      "#DCC83C",
    "btn_bg":    "#C49638",
    "btn_fg":    "#0E0C0A",
    "btn_dim":   "#5A4A20",
    "sep":       "#5A4020",
    "online":    "#50C864",
    "offline":   "#DC503C",
    "log_bg":    "#06050403",
    "tab_act":   "#C49638",
    "tab_inact": "#2A2018",
    "coffee":    "#FFCC00",
}

APP_VERSION = "2.0.0"
APP_TITLE   = f"Dragonwilds Server Manager  v{APP_VERSION}"


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def _styled_button(parent, text, command, bg=None, fg=None, width=None, font=None):
    kw = dict(
        text=text, command=command,
        bg=bg or P["btn_bg"], fg=fg or P["btn_fg"],
        activebackground=P["accent2"], activeforeground=P["text"],
        relief="flat", bd=0, cursor="hand2",
        padx=12, pady=6,
        font=font or ("Segoe UI", 9, "bold"),
    )
    if width:
        kw["width"] = width
    btn = tk.Button(parent, **kw)
    return btn


def _label(parent, text, font=None, fg=None, bg=None, anchor="w", **kw):
    return tk.Label(
        parent, text=text,
        font=font or ("Segoe UI", 9),
        fg=fg or P["text"],
        bg=bg or P["panel"],
        anchor=anchor, **kw,
    )


def _entry(parent, textvariable, show="", width=32, font=None):
    return tk.Entry(
        parent, textvariable=textvariable,
        bg=P["input_bg"], fg=P["text"],
        insertbackground=P["accent"],
        relief="flat", bd=4, show=show,
        width=width,
        font=font or ("Segoe UI", 9),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG WIDGET  (shared across tabs)
# ═══════════════════════════════════════════════════════════════════════════════

class LogWidget(scrolledtext.ScrolledText):
    TAG_COLORS = {
        "OK":    P["success"],
        "ERROR": P["error"],
        "WARN":  P["warn"],
        "INFO":  P["text"],
    }

    def __init__(self, parent, **kw):
        super().__init__(
            parent,
            bg="#060504", fg=P["text"],
            font=("Consolas", 8),
            relief="flat", bd=0,
            state="disabled",
            wrap="word",
            **kw,
        )
        for tag, color in self.TAG_COLORS.items():
            self.tag_config(tag, foreground=color)

    def append(self, message: str, level: str = "INFO"):
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}][{level}] {message}\n"
        self.configure(state="normal")
        self.insert("end", line, level)
        self.configure(state="disabled")
        self.see("end")


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS TAB
# ═══════════════════════════════════════════════════════════════════════════════

class StatusTab(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=P["panel"])
        self.app = app
        self._build()

    def _build(self):
        # ── Big status indicator ──
        top = tk.Frame(self, bg=P["panel"], pady=20)
        top.pack(fill="x", padx=24)

        self._dot = tk.Label(top, text="●", font=("Segoe UI", 36),
                             bg=P["panel"], fg=P["offline"])
        self._dot.pack(side="left", padx=(0, 16))

        info = tk.Frame(top, bg=P["panel"])
        info.pack(side="left", fill="y")

        self._status_lbl = tk.Label(info, text="Server Offline",
                                    font=("Georgia", 18, "bold"),
                                    bg=P["panel"], fg=P["offline"], anchor="w")
        self._status_lbl.pack(anchor="w")

        self._uptime_lbl = tk.Label(info, text="Uptime: --",
                                    font=("Segoe UI", 9),
                                    bg=P["panel"], fg=P["subtext"], anchor="w")
        self._uptime_lbl.pack(anchor="w")

        self._pid_lbl = tk.Label(info, text="PID: --",
                                 font=("Consolas", 8),
                                 bg=P["panel"], fg=P["subtext"], anchor="w")
        self._pid_lbl.pack(anchor="w")

        # ── Server path display ──
        tk.Frame(self, bg=P["sep"], height=1).pack(fill="x", padx=24)

        path_frame = tk.Frame(self, bg=P["panel"], pady=10)
        path_frame.pack(fill="x", padx=24)

        _label(path_frame, "Server Executable:", fg=P["subtext"]).pack(anchor="w")
        self._path_lbl = _label(path_frame, "Not configured",
                                font=("Consolas", 8), fg=P["accent"])
        self._path_lbl.pack(anchor="w")

        # ── World name display ──
        self._world_lbl = _label(path_frame, "",
                                 font=("Segoe UI", 9), fg=P["subtext"])
        self._world_lbl.pack(anchor="w", pady=(4, 0))

        # ── Action buttons ──
        tk.Frame(self, bg=P["sep"], height=1).pack(fill="x", padx=24)

        btn_row = tk.Frame(self, bg=P["panel"], pady=14)
        btn_row.pack(fill="x", padx=24)

        self._btn_start = _styled_button(btn_row, "[>]  Start Server",
                                         self.app.start_server, width=20)
        self._btn_start.pack(side="left", padx=(0, 8))

        self._btn_stop = _styled_button(btn_row, "[X]  Stop Server",
                                        self.app.stop_server,
                                        bg=P["btn_dim"], fg=P["text"], width=20)
        self._btn_stop.pack(side="left", padx=(0, 8))

        _styled_button(btn_row, "[F]  Open Server Folder",
                       self.app.open_folder, bg=P["panel2"], fg=P["text"], width=22
                       ).pack(side="left")

        # ── Log ──
        tk.Frame(self, bg=P["sep"], height=1).pack(fill="x", padx=24, pady=(4, 0))
        _label(self, "Live Log", fg=P["subtext"], bg=P["panel"],
               font=("Segoe UI", 8)).pack(anchor="w", padx=26, pady=(6, 0))
        self.app.log.pack(in_=self, fill="both", expand=True, padx=24, pady=(2, 10))

    def refresh(self, mon: monitor.ServerMonitor):
        """Called by the monitor tick -- update all status widgets."""
        if mon.is_online:
            self._dot.configure(fg=P["online"])
            self._status_lbl.configure(text="Server Online", fg=P["online"])
            self._uptime_lbl.configure(text=f"Uptime: {mon.uptime_str}")
            self._pid_lbl.configure(text=f"PID: {mon.pid}")
            self._btn_start.configure(state="disabled", bg=P["btn_dim"])
            self._btn_stop.configure(state="normal",   bg="#6E2020")
            if mon.exe_path:
                self._path_lbl.configure(text=mon.exe_path)
        else:
            self._dot.configure(fg=P["offline"])
            self._status_lbl.configure(text="Server Offline", fg=P["offline"])
            self._uptime_lbl.configure(text="Uptime: --")
            self._pid_lbl.configure(text="PID: --")
            self._btn_start.configure(state="normal",   bg=P["btn_bg"])
            self._btn_stop.configure(state="disabled",  bg=P["btn_dim"])

        cfg = self.app.prefs
        exe = cfg.get("server_exe") or "Not configured"
        self._path_lbl.configure(text=exe)
        world = cfg.get("world_name", "")
        self._world_lbl.configure(
            text=f"World: {world}" if world else ""
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  SETUP TAB
# ═══════════════════════════════════════════════════════════════════════════════

class SetupTab(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=P["panel"])
        self.app = app
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 4}

        # Install dir row
        tk.Frame(self, bg=P["sep"], height=1).pack(fill="x", padx=24, pady=(16, 4))
        _label(self, "Installation", font=("Segoe UI", 10, "bold"),
               bg=P["panel"], fg=P["accent"]).pack(anchor="w", **pad)

        dir_row = tk.Frame(self, bg=P["panel"])
        dir_row.pack(fill="x", **pad)
        _label(dir_row, "Install Folder:", fg=P["subtext"], width=18).pack(side="left")
        self._install_dir_var = tk.StringVar(value=self.app.prefs.get("install_dir", str(Path.home() / "DragonWildsServer")))
        _entry(dir_row, self._install_dir_var, width=40).pack(side="left", padx=(4, 6))
        _styled_button(dir_row, "Browse", self._browse_install,
                       bg=P["panel2"], fg=P["text"]).pack(side="left")

        # Existing server row
        exist_row = tk.Frame(self, bg=P["panel"])
        exist_row.pack(fill="x", **pad)
        _label(exist_row, "Existing Server Exe:", fg=P["subtext"], width=18).pack(side="left")
        self._exe_var = tk.StringVar(value=self.app.prefs.get("server_exe", ""))
        _entry(exist_row, self._exe_var, width=40).pack(side="left", padx=(4, 6))
        _styled_button(exist_row, "Browse", self._browse_exe,
                       bg=P["panel2"], fg=P["text"]).pack(side="left")

        tk.Label(self, text="  Point to an existing RSDragonwilds.exe to skip installation",
                 font=("Segoe UI", 7, "italic"), bg=P["panel"], fg=P["subtext"],
                 anchor="w").pack(fill="x", padx=60)

        # Action buttons
        tk.Frame(self, bg=P["sep"], height=1).pack(fill="x", padx=24, pady=(12, 4))
        _label(self, "Actions", font=("Segoe UI", 10, "bold"),
               bg=P["panel"], fg=P["accent"]).pack(anchor="w", **pad)

        btn_grid = tk.Frame(self, bg=P["panel"])
        btn_grid.pack(fill="x", **pad)

        self._btn_full = _styled_button(btn_grid, "[*]  Full Setup",
                                        self.app.run_full_setup, width=22)
        self._btn_full.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

        _styled_button(btn_grid, "[S]  Firewall Only",
                       self.app.run_firewall_only,
                       bg=P["panel2"], fg=P["text"], width=22
                       ).grid(row=0, column=1, padx=(0, 8), pady=4, sticky="w")

        _styled_button(btn_grid, "[C]  Save Config Only",
                       self.app.save_config_only,
                       bg=P["panel2"], fg=P["text"], width=22
                       ).grid(row=1, column=0, padx=(0, 8), pady=4, sticky="w")

        _styled_button(btn_grid, "[U]  Update Server Files",
                       self.app.run_update,
                       bg=P["panel2"], fg=P["text"], width=22
                       ).grid(row=1, column=1, padx=(0, 8), pady=4, sticky="w")

        _styled_button(btn_grid, "[!]  Delete Server Files",
                       self.app.delete_server_files,
                       bg="#6E2020", fg=P["text"], width=22
                       ).grid(row=2, column=0, padx=(0, 8), pady=4, sticky="w")

        # Progress bar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("D.Horizontal.TProgressbar",
                        troughcolor=P["panel2"], background=P["accent"],
                        bordercolor=P["bg"])
        self.progress = ttk.Progressbar(self, style="D.Horizontal.TProgressbar",
                                        mode="indeterminate")
        self.progress.pack(fill="x", padx=24, pady=(8, 2))

        self._status_lbl = _label(self, "Ready.", fg=P["subtext"], bg=P["panel"])
        self._status_lbl.pack(anchor="w", padx=24)

    def _browse_install(self):
        d = filedialog.askdirectory(title="Choose install folder",
                                    initialdir=self._install_dir_var.get())
        if d:
            self._install_dir_var.set(d)
            self.app.prefs["install_dir"] = d
            settings.save(self.app.prefs)

    def _browse_exe(self):
        f = filedialog.askopenfilename(
            title="Select RSDragonwilds.exe",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if f:
            self._exe_var.set(f)
            self.app.prefs["server_exe"] = f
            settings.save(self.app.prefs)

    def set_status(self, text: str, color: str = None):
        self._status_lbl.configure(text=text, fg=color or P["subtext"])

    def start_progress(self):
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        for btn in (self._btn_full,):
            btn.configure(state="disabled", bg=P["btn_dim"])

    def stop_progress(self, pct: float = 100):
        self.progress.stop()
        self.progress.configure(mode="determinate", value=pct)
        self._btn_full.configure(state="normal", bg=P["btn_bg"])

    def get_install_dir(self) -> Path:
        return Path(self._install_dir_var.get())

    def get_exe_override(self) -> str:
        return self._exe_var.get().strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG TAB
# ═══════════════════════════════════════════════════════════════════════════════

class ConfigTab(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=P["panel"])
        self.app = app
        self._vars = {}
        self._build()
        self._load_into_fields()

    def _field(self, parent, key, label, hint="", row=0, is_pass=False, highlight=False):
        fg  = P["accent"] if highlight else P["subtext"]
        efg = P["accent"] if highlight else P["text"]

        tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"),
                 bg=P["panel"], fg=fg, anchor="e", width=22
                 ).grid(row=row, column=0, sticky="e", padx=(0, 8), pady=5)

        var = tk.StringVar(value=self.app.prefs.get(key, ""))
        self._vars[key] = var

        e = tk.Entry(parent, textvariable=var,
                     bg=P["input_bg"], fg=efg,
                     insertbackground=P["accent"],
                     relief="flat", bd=4, width=36,
                     font=("Consolas", 9) if highlight else ("Segoe UI", 9),
                     show="*" if is_pass else "")
        e.grid(row=row, column=1, sticky="w", pady=5)

        if hint:
            tk.Label(parent, text=hint, font=("Segoe UI", 7, "italic"),
                     bg=P["panel"], fg=P["subtext"]
                     ).grid(row=row, column=2, sticky="w", padx=(8, 0))

    def _build(self):
        pad = {"padx": 24, "pady": 4}
        tk.Frame(self, bg=P["sep"], height=1).pack(fill="x", padx=24, pady=(16, 8))
        _label(self, "Server Configuration", font=("Segoe UI", 10, "bold"),
               bg=P["panel"], fg=P["accent"]).pack(anchor="w", **pad)

        grid = tk.Frame(self, bg=P["panel"])
        grid.pack(fill="x", padx=24)

        fields = [
            ("owner_id",    "Player ID (Owner) *", "In-game -> Settings -> bottom",  True,  False),
            ("server_name", "Server Name *",        "Shown in server browser",         False, False),
            ("world_name",  "Default World Name *", "Search this exactly in-game",     False, False),
            ("admin_pass",  "Admin Password *",     "Pause -> Server Management",      False, True),
            ("world_pass",  "World Password",       "Leave blank for public server",   False, True),
            ("port",        "Server Port",          "UDP 7777 default",                False, False),
        ]
        for i, (key, lbl, hint, hi, pw) in enumerate(fields):
            self._field(grid, key, lbl, hint, row=i, is_pass=pw, highlight=hi)

        # Save button
        tk.Frame(self, bg=P["sep"], height=1).pack(fill="x", padx=24, pady=(12, 8))
        btn_row = tk.Frame(self, bg=P["panel"])
        btn_row.pack(fill="x", padx=24)

        _styled_button(btn_row, "[S]  Save Configuration", self._save, width=24).pack(side="left", padx=(0, 12))
        _styled_button(btn_row, "[R]  Reload from File", self._reload,
                       bg=P["panel2"], fg=P["text"], width=22).pack(side="left")

        self._saved_lbl = _label(self, "", fg=P["success"], bg=P["panel"])
        self._saved_lbl.pack(anchor="w", padx=24, pady=(6, 0))

    def _load_into_fields(self):
        data = installer.read_config()

        if self.app.prefs.get("server_exe"):
            for ext_cfg in installer._dedicated_config_paths_from_exe(self.app.prefs["server_exe"]):
                if ext_cfg.exists():
                    ext_data = installer.read_config(ext_cfg)
                    for key, value in ext_data.items():
                        if value:
                            data[key] = value

        for key, var in self._vars.items():
            value = data.get(key) or self.app.prefs.get(key, "")
            if value:
                var.set(value)
                self.app.prefs[key] = value

    def _save(self):
        for key, var in self._vars.items():
            self.app.prefs[key] = var.get().strip()
        settings.save(self.app.prefs)
        installer.write_config(self.app.prefs, self.app.log.append)
        self._saved_lbl.configure(text="Saved and written to DedicatedServer.ini")
        self.after(3000, lambda: self._saved_lbl.configure(text=""))

    def _reload(self):
        self._load_into_fields()
        settings.save(self.app.prefs)
        self._saved_lbl.configure(text="Reloaded from DedicatedServer.ini", fg=P["warn"])
        self.after(3000, lambda: self._saved_lbl.configure(text=""))

    def get_cfg(self) -> dict:
        return {k: v.get().strip() for k, v in self._vars.items()}

    def validate(self) -> list[str]:
        cfg  = self.get_cfg()
        errs = []
        if not cfg.get("owner_id"):    errs.append("Player ID is required.")
        if not cfg.get("server_name"): errs.append("Server Name is required.")
        if not cfg.get("world_name"):  errs.append("Default World Name is required.")
        if not cfg.get("admin_pass"):  errs.append("Admin Password is required.")
        return errs


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

class DragonwildsManager(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=P["bg"])
        self.resizable(True, True)
        self.minsize(740, 620)

        self.prefs = settings.load()

        # Merge existing DedicatedServer.ini values into any empty preference fields.
        # This keeps the UI populated on startup without overwriting saved app settings.
        data = installer.read_config()

        # If the game install tree has its own dedicated config, merge that too.
        if self.prefs.get("server_exe"):
            for ext_cfg in installer._dedicated_config_paths_from_exe(self.prefs["server_exe"]):
                if ext_cfg.exists():
                    ext_data = installer.read_config(ext_cfg)
                    for k, v in ext_data.items():
                        if v:
                            data[k] = v

        for k, v in data.items():
            if v and not self.prefs.get(k):
                self.prefs[k] = v

        self.monitor = monitor.ServerMonitor(poll_interval=3)
        self.log = LogWidget(self, height=10)

        self._build_ui()
        self._start_monitor()
        self._restore_geometry()

        self.log.append(f"Dragonwilds Server Manager v{APP_VERSION} ready.")
        if not is_admin():
            self.log.append("Not running as Administrator -- firewall changes may fail.", "WARN")
            self.log.append("Right-click the app and choose Run as Administrator for full functionality.", "WARN")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        title_frame = tk.Frame(self, bg=P["bg"], pady=10)
        title_frame.pack(fill="x", padx=20)
        tk.Label(title_frame, text="RS: Dragonwilds",
                 font=("Georgia", 18, "bold"),
                 bg=P["bg"], fg=P["accent"]).pack(side="left")
        tk.Label(title_frame, text="  Server Manager",
                 font=("Segoe UI", 13),
                 bg=P["bg"], fg=P["text"]).pack(side="left")
        tk.Label(title_frame, text=f"v{APP_VERSION}",
                 font=("Segoe UI", 8),
                 bg=P["bg"], fg=P["subtext"]).pack(side="left", padx=(8, 0), anchor="s")

        tk.Frame(self, bg=P["sep"], height=2).pack(fill="x")

        # Tabs
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("D.TNotebook",        background=P["bg"],    borderwidth=0)
        style.configure("D.TNotebook.Tab",    background=P["panel2"], foreground=P["subtext"],
                        padding=[16, 6],      font=("Segoe UI", 9, "bold"))
        style.map("D.TNotebook.Tab",
                  background=[("selected", P["panel"])],
                  foreground=[("selected", P["accent"])])

        nb = ttk.Notebook(self, style="D.TNotebook")
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        self.tab_status = StatusTab(nb, self)
        self.tab_setup  = SetupTab(nb, self)
        self.tab_config = ConfigTab(nb, self)

        nb.add(self.tab_status, text="  Status  ")
        nb.add(self.tab_setup,  text="  Setup   ")
        nb.add(self.tab_config, text="  Config  ")

        # Bottom bar
        tk.Frame(self, bg=P["sep"], height=2).pack(fill="x")
        bottom = tk.Frame(self, bg="#1A1200", pady=3)
        bottom.pack(fill="x")

        tk.Label(bottom,
                 text="TIP: Player ID is found in-game -> Settings -> scroll to the very bottom",
                 font=("Segoe UI", 7), bg="#1A1200", fg=P["warn"]
                 ).pack(side="left", padx=12)

        coffee = tk.Label(bottom,
                          text="Buy me a coffee  buymeacoffee.com/obietek",
                          font=("Segoe UI", 7, "underline"),
                          bg="#1A1200", fg=P["coffee"], cursor="hand2")
        coffee.pack(side="right", padx=12)
        coffee.bind("<Button-1>", lambda _: webbrowser.open("https://buymeacoffee.com/obietek"))

    # ── Monitor ───────────────────────────────────────────────────────────────

    def _start_monitor(self):
        self.monitor.on_tick = self._on_monitor_tick
        self.monitor.on_status_change = self._on_status_change
        self.monitor.start()

    def _on_monitor_tick(self):
        # Called from background thread -- schedule UI update on main thread
        self.after(0, self._refresh_status_tab)

    def _on_status_change(self, is_online: bool):
        if is_online:
            self.after(0, lambda: self.log.append("Server process detected -- now online.", "OK"))
        else:
            self.after(0, lambda: self.log.append("Server process stopped -- now offline.", "WARN"))

    def _refresh_status_tab(self):
        self.tab_status.refresh(self.monitor)

    # ── Actions ───────────────────────────────────────────────────────────────

    def start_server(self):
        # Resolve exe path
        exe = self.tab_setup.get_exe_override() or self.prefs.get("server_exe", "")
        if not exe or not Path(exe).exists():
            # Try to find it
            install_dir = Path(self.prefs.get("install_dir", str(Path.home() / "DragonWildsServer")))
            exe = installer.find_server_exe(install_dir) or ""

        if not exe or not Path(exe).exists():
            messagebox.showerror(
                "Server Not Found",
                "Cannot find RSDragonwilds.exe.\n\n"
                "Either:\n"
                "  1. Run Full Setup on the Setup tab to install it.\n"
                "  2. Browse to an existing exe on the Setup tab.",
            )
            return

        # Save resolved path
        self.prefs["server_exe"] = exe
        settings.save(self.prefs)

        # Write config before launch
        cfg  = self.tab_config.get_cfg()
        errs = self.tab_config.validate()

        # Keep app preferences in sync and persist them for later runs.
        self.prefs.update(cfg)
        settings.save(self.prefs)

        if errs:
            if not messagebox.askyesno(
                "Incomplete Config",
                "Some required config fields are empty:\n\n" + "\n".join(errs) +
                "\n\nLaunch anyway?",
            ):
                return

        installer.write_config(self.prefs, self.log.append)

        self.log.append(f"Launching: {exe}")
        subprocess.Popen([exe, "-log", "-NewConsole"])
        self.log.append("Server launched -- monitoring for process...", "OK")

    def stop_server(self):
        if not self.monitor.is_online:
            return
        if messagebox.askyesno("Stop Server", "Are you sure you want to stop the server?"):
            ok = self.monitor.kill()
            if ok:
                self.log.append("Server stopped.", "OK")
            else:
                self.log.append("Could not stop server -- try killing it manually in Task Manager.", "ERROR")

    def open_folder(self):
        exe = self.prefs.get("server_exe", "")
        folder = str(Path(exe).parent) if exe else self.prefs.get("install_dir", str(Path.home() / "DragonWildsServer"))
        if Path(folder).exists():
            os.startfile(folder)
        else:
            messagebox.showinfo("Not Found", f"Folder not found:\n{folder}")

    def run_full_setup(self):
        errs = self.tab_config.validate()
        if errs:
            messagebox.showwarning("Missing Config", "\n".join(errs))
            return

        def _worker():
            self.after(0, self.tab_setup.start_progress)
            self.after(0, lambda: self.tab_setup.set_status("Running full setup...", P["warn"]))

            install_dir  = self.tab_setup.get_install_dir()
            steamcmd_dir = install_dir / "steamcmd"

            # Step 1 - SteamCMD
            self.log.append("=== STEP 1/4: SteamCMD ===")
            if (steamcmd_dir / "steamcmd.exe").exists():
                self.log.append("SteamCMD already present -- skipping.", "OK")
            else:
                ok = installer.download_steamcmd(steamcmd_dir, self.log.append)
                if not ok:
                    self.after(0, lambda: self.tab_setup.stop_progress(0))
                    self.after(0, lambda: self.tab_setup.set_status("Failed at SteamCMD step.", P["error"]))
                    return

            # Step 2 - Server files
            self.log.append("=== STEP 2/4: Server Files ===")
            ok = installer.install_server(install_dir, steamcmd_dir, self.log.append)
            if not ok:
                self.after(0, lambda: self.tab_setup.stop_progress(0))
                self.after(0, lambda: self.tab_setup.set_status("Failed at server install step.", P["error"]))
                return

            # Save resolved exe
            found = installer.find_server_exe(install_dir)
            if found:
                self.prefs["server_exe"] = found

            # Step 3 - Config
            self.log.append("=== STEP 3/4: Configuration ===")
            cfg = self.tab_config.get_cfg()
            self.prefs.update(cfg)
            settings.save(self.prefs)
            installer.write_config(self.prefs, self.log.append)

            # Step 4 - Firewall
            self.log.append("=== STEP 4/4: Firewall ===")
            port = int(cfg.get("port", 7777))
            installer.set_firewall(port, self.log.append)

            settings.save(self.prefs)
            self.after(0, lambda: self.tab_setup.stop_progress(100))
            self.after(0, lambda: self.tab_setup.set_status("Setup complete! Go to Status tab to launch.", P["success"]))
            self.log.append("Full setup complete!", "OK")

        threading.Thread(target=_worker, daemon=True).start()

    def run_firewall_only(self):
        cfg  = self.tab_config.get_cfg()
        port = int(cfg.get("port", 7777))

        def _worker():
            installer.set_firewall(port, self.log.append)
            self.after(0, lambda: self.tab_setup.set_status(f"Firewall rules updated for UDP {port}.", P["success"]))

        threading.Thread(target=_worker, daemon=True).start()

    def run_update(self):
        install_dir  = self.tab_setup.get_install_dir()
        steamcmd_dir = install_dir / "steamcmd"

        def _worker():
            self.after(0, self.tab_setup.start_progress)
            self.after(0, lambda: self.tab_setup.set_status("Updating server files...", P["warn"]))
            ok = installer.install_server(install_dir, steamcmd_dir, self.log.append)
            self.after(0, lambda: self.tab_setup.stop_progress(100 if ok else 0))
            msg = "Update complete!" if ok else "Update failed -- check the log."
            color = P["success"] if ok else P["error"]
            self.after(0, lambda: self.tab_setup.set_status(msg, color))

        threading.Thread(target=_worker, daemon=True).start()

    def save_config_only(self):
        cfg  = self.tab_config.get_cfg()
        errs = self.tab_config.validate()
        if errs:
            messagebox.showwarning("Missing Config", "\n".join(errs))
            return
        self.prefs.update(cfg)
        settings.save(self.prefs)
        installer.write_config(self.prefs, self.log.append)
        self.tab_setup.set_status("Config saved.", P["success"])

    def delete_server_files(self):
        install_dir = self.tab_setup.get_install_dir()

        if self.monitor.is_online:
            messagebox.showwarning(
                "Server Running",
                "Stop the server before deleting its files.",
            )
            return

        if not install_dir.exists():
            messagebox.showinfo(
                "Nothing To Delete",
                f"The install folder does not exist:\n{install_dir}",
            )
            return

        if not messagebox.askyesno(
            "Delete Server Files",
            "This will permanently delete the configured server install folder and all files inside it.\n\n"
            f"Folder:\n{install_dir}\n\n"
            "Do you want to continue?",
            icon="warning",
        ):
            return

        def _worker():
            self.after(0, self.tab_setup.start_progress)
            self.after(0, lambda: self.tab_setup.set_status("Deleting server files...", P["warn"]))
            ok = installer.delete_server_files(install_dir, self.log.append)

            if ok:
                self.prefs["server_exe"] = ""
                self.after(0, lambda: self.tab_setup._exe_var.set(""))
                settings.save(self.prefs)

            self.after(0, lambda: self.tab_setup.stop_progress(100 if ok else 0))
            msg = "Server files deleted." if ok else "Delete failed -- check the log."
            color = P["success"] if ok else P["error"]
            self.after(0, lambda: self.tab_setup.set_status(msg, color))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Window state ──────────────────────────────────────────────────────────

    def _restore_geometry(self):
        x = self.prefs.get("window_x", -1)
        y = self.prefs.get("window_y", -1)
        self.geometry("820x680")
        if x >= 0 and y >= 0:
            self.geometry(f"+{x}+{y}")
        else:
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            cx = (sw - 820) // 2
            cy = (sh - 680) // 2
            self.geometry(f"820x680+{cx}+{cy}")

    def _on_close(self):
        self.prefs["window_x"] = self.winfo_x()
        self.prefs["window_y"] = self.winfo_y()
        settings.save(self.prefs)
        self.monitor.stop()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = DragonwildsManager()
    app.mainloop()
