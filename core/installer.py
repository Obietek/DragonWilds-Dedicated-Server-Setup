"""
core/installer.py
All SteamCMD download, server install, config write, and firewall logic.
"""

import os
import shutil
import subprocess
import textwrap
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


STEAM_CMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
STEAM_APP_ID  = "4019830"
SERVER_EXE    = "RSDragonwildsServer.exe"
STEAM_APP_DIR = "RuneScape Dragonwilds Dedicated Server"

LOCAL_APP     = Path(os.getenv("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"))
CONFIG_WIN    = LOCAL_APP / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer"
CONFIG_FILE   = CONFIG_WIN / "DedicatedServer.ini"
SAVEGAMES_DIR = LOCAL_APP / "RSDragonwilds" / "Saved" / "SaveGames"


# ──────────────────────────────────────────────────────────────────────────────
# SteamCMD
# ──────────────────────────────────────────────────────────────────────────────

def download_steamcmd(steamcmd_dir: Path, log, progress_cb=None) -> bool:
    log("Downloading SteamCMD...")
    steamcmd_dir.mkdir(parents=True, exist_ok=True)
    zip_path = steamcmd_dir / "steamcmd.zip"
    try:
        def _reporthook(block, block_size, total):
            if progress_cb and total > 0:
                progress_cb(block * block_size, total)

        urllib.request.urlretrieve(STEAM_CMD_URL, zip_path, _reporthook)
        log("Extracting SteamCMD...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(steamcmd_dir)
        zip_path.unlink(missing_ok=True)
        log(f"SteamCMD ready at {steamcmd_dir}", "OK")
        return True
    except Exception as exc:
        log(f"SteamCMD download failed: {exc}", "ERROR")
        return False


def install_server(install_dir: Path, steamcmd_dir: Path, log) -> bool:
    exe = steamcmd_dir / "steamcmd.exe"
    if not exe.exists():
        log("steamcmd.exe not found.", "ERROR")
        return False

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        log(f"Install directory: {install_dir}", "OK")
    except Exception as exc:
        log(f"Cannot create install directory {install_dir}: {exc}", "ERROR")
        log("Try running as Administrator or choose a different install folder.", "ERROR")
        return False

    log(f"Installing server files (App {STEAM_APP_ID})...")
    log("This can take several minutes -- please wait...", "WARN")

    cmd = [
        str(exe),
        "+force_install_dir", str(install_dir),
        "+login", "anonymous",
        "+app_update", STEAM_APP_ID,
        "validate",
        "+quit",
    ]
    result = subprocess.run(cmd, capture_output=False, text=True)

    # SteamCMD exits with code 7 on first run while it self-updates; retry once.
    if result.returncode == 7:
        log("SteamCMD updated itself -- retrying install...", "WARN")
        result = subprocess.run(cmd, capture_output=False, text=True)

    if result.returncode == 0:
        log("Server files installed.", "OK")
        found = find_server_exe(install_dir)
        if found:
            log(f"Exe confirmed at: {found}", "OK")
        else:
            log("WARNING: exe not found after install -- check the install folder.", "WARN")
            _list_dir(install_dir, log)
        return True
    else:
        log(f"SteamCMD exited with code {result.returncode}.", "ERROR")
        return False


def find_server_exe(install_dir: Path):
    """Search common locations for RSDragonwildsServer.exe and return its path or None."""
    candidates = [
        # SteamCMD installs into its own steamapps folder inside steamcmd_dir
        install_dir / "steamcmd" / "steamapps" / "common" / STEAM_APP_DIR / SERVER_EXE,
        # Direct install (if force_install_dir puts files at root)
        install_dir / SERVER_EXE,
        install_dir / "steamapps" / "common" / STEAM_APP_DIR / SERVER_EXE,
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # Recursive search under install_dir
    for match in install_dir.rglob(SERVER_EXE):
        return str(match)

    return None


def delete_server_files(install_dir: Path, log) -> bool:
    """Delete the configured server install directory after basic safety checks."""
    try:
        target = Path(install_dir).resolve()
    except Exception as exc:
        log(f"Could not resolve install directory: {exc}", "ERROR")
        return False

    if not target.exists():
        log(f"Install directory does not exist: {target}", "WARN")
        return True

    if not target.is_dir():
        log(f"Install path is not a directory: {target}", "ERROR")
        return False

    # Refuse obviously dangerous targets.
    if target == target.anchor or len(target.parts) < 2:
        log(f"Refusing to delete unsafe path: {target}", "ERROR")
        return False

    try:
        log(f"Deleting server files from {target}...", "WARN")
        shutil.rmtree(target)
        log("Server files deleted.", "OK")
        return True
    except Exception as exc:
        log(f"Failed to delete server files: {exc}", "ERROR")
        return False


def _list_dir(path: Path, log, depth: int = 0, max_depth: int = 3):
    try:
        indent = "  " * (depth + 1)
        for item in path.iterdir():
            log(f"{indent}{item.name}{'/' if item.is_dir() else ''}")
            if item.is_dir() and depth < max_depth:
                _list_dir(item, log, depth + 1, max_depth)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

def _dedicated_config_paths_from_exe(exe_path: str) -> list[Path]:
    exe_path = str(exe_path).strip()
    if not exe_path:
        return []
    p = Path(exe_path)
    if not p.is_file():
        return []
    base = p.parent
    return [
        base / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer" / "DedicatedServer.ini",
        base / "Saved" / "Config" / "WindowsServer" / "DedicatedServer.ini",
    ]


def dedicated_savegames_paths_from_exe(exe_path: str) -> list[Path]:
    exe_path = str(exe_path).strip()
    if not exe_path:
        return []
    p = Path(exe_path)
    if not p.is_file():
        return []
    base = p.parent
    return [
        base / "RSDragonwilds" / "Saved" / "SaveGames",
        base / "Saved" / "SaveGames",
    ]


def backup_savegames(destination_root: Path, exe_path: str, log) -> bool:
    destination_root = Path(destination_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = destination_root / f"DragonwildsBackup-{stamp}"
    backup_root.mkdir(parents=True, exist_ok=True)

    sources: list[tuple[str, Path]] = []
    if SAVEGAMES_DIR.exists():
        sources.append(("LocalSaveGames", SAVEGAMES_DIR))

    for path in dedicated_savegames_paths_from_exe(exe_path):
        if path.exists():
            label = "DedicatedSaveGames"
            if any(name == label for name, _ in sources):
                label = f"{label}-{path.parent.parent.name}"
            sources.append((label, path))

    if not sources:
        log("No SaveGames folders were found to back up.", "WARN")
        return False

    for label, src in sources:
        dest = backup_root / label
        shutil.copytree(src, dest, dirs_exist_ok=True)
        log(f"Backed up {src} to {dest}", "OK")

    log(f"Backup complete: {backup_root}", "OK")
    return True


def write_config(cfg: dict, log) -> None:
    log("Writing DedicatedServer.ini...")
    CONFIG_WIN.mkdir(parents=True, exist_ok=True)
    SAVEGAMES_DIR.mkdir(parents=True, exist_ok=True)

    owner_id = str(cfg.get("owner_id", "")).strip()
    server_name = str(cfg.get("server_name", "")).strip()
    world_name = str(cfg.get("world_name", "")).strip()
    admin_pass = str(cfg.get("admin_pass", "")).strip()
    world_pass = str(cfg.get("world_pass", "")).strip()
    port = str(cfg.get("port", "7777")).strip() or "7777"

    content = textwrap.dedent(f"""\
        ;METADATA=(Diff=true, UseCommands=true)
        [SectionsToSave]
        bCanSaveAllSections=true

        [/Script/Dominion.DedicatedServerSettings]
        AdminPassword={admin_pass}
        OwnerId={owner_id}
        WorldPassword={world_pass}
        ServerName={server_name}
        DefaultWorldName={world_name}
        Port={port}

        [/Script/RSDragonwilds.DedicatedServerConfig]
        OwnerID={owner_id}
        ServerName={server_name}
        DefaultWorldName={world_name}
        AdminPassword={admin_pass}
        WorldPassword={world_pass}
        Port={port}
    """)

    # Primary config location (LocalAppData)
    CONFIG_FILE.write_text(content, encoding="utf-8")
    log(f"Config written to {CONFIG_FILE}", "OK")

    # Secondary locations under the server install tree, if applicable.
    for exe_cfg_path in _dedicated_config_paths_from_exe(cfg.get("server_exe", "")):
        exe_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        exe_cfg_path.write_text(content, encoding="utf-8")
        log(f"Config also written to {exe_cfg_path}", "OK")


def read_config(config_path: Path = None) -> dict:
    """Read existing DedicatedServer.ini and return a dict of values."""
    defaults = {
        "owner_id": "", "server_name": "", "world_name": "",
        "admin_pass": "", "world_pass": "", "port": "7777",
    }
    key_map = {
        "ownerid": "owner_id", "servername": "server_name",
        "defaultworldname": "world_name", "adminpassword": "admin_pass",
        "worldpassword": "world_pass", "port": "port",
    }

    target = Path(config_path) if config_path else CONFIG_FILE
    if not target.exists():
        return defaults

    for line in target.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            mapped = key_map.get(k.strip().lower())
            if mapped:
                defaults[mapped] = v.strip()
    return defaults


# ──────────────────────────────────────────────────────────────────────────────
# Firewall
# ──────────────────────────────────────────────────────────────────────────────

def set_firewall(port: int, log) -> None:
    log(f"Configuring Windows Firewall for UDP {port}...")
    for direction in ("in", "out"):
        name = f"RSDragonwilds-UDP-{port}-{direction}"
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"],
            capture_output=True,
        )
        result = subprocess.run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={name}", f"dir={direction}", "action=allow",
            "protocol=UDP", f"localport={port}", "profile=any", "enable=yes",
        ], capture_output=True, text=True)
        if result.returncode == 0:
            log(f"Firewall rule '{name}' created.", "OK")
        else:
            log(f"Failed to create '{name}': {result.stderr.strip()}", "ERROR")
    log(f"Firewall done. Remember to forward UDP {port} on your router!", "WARN")
