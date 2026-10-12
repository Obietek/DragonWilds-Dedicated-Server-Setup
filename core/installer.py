"""
core/installer.py
All SteamCMD download, server install, config write, and firewall logic.
"""

import os
import shutil
import subprocess
import sys
import tarfile
import textwrap
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


STEAM_CMD_URL_WINDOWS = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
STEAM_CMD_URL_LINUX = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
STEAM_APP_ID  = "4019830"
IS_WINDOWS    = sys.platform == "win32"
IS_LINUX      = sys.platform.startswith("linux")
SERVER_EXE    = "RSDragonwildsServer.exe" if IS_WINDOWS else "RSDragonwildsServer"
STEAM_APP_DIR = "RuneScape Dragonwilds Dedicated Server"

if IS_WINDOWS:
    LOCAL_APP = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    CONFIG_PLATFORM = "WindowsServer"
    SAVE_APP = LOCAL_APP
elif IS_LINUX:
    # The Linux server only reads the config inside its install folder
    # (<root>/RSDragonwilds/Saved), so there is no per-user config file.
    LOCAL_APP = None
    CONFIG_PLATFORM = "LinuxServer"
    SAVE_APP = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
else:
    LOCAL_APP = Path.home() / "Library" / "Application Support"
    CONFIG_PLATFORM = "LinuxServer"
    SAVE_APP = LOCAL_APP

if LOCAL_APP is None:
    CONFIG_DIR = CONFIG_FILE = None
else:
    CONFIG_DIR = LOCAL_APP / "RSDragonwilds" / "Saved" / "Config" / CONFIG_PLATFORM
    CONFIG_FILE = CONFIG_DIR / "DedicatedServer.ini"
SAVEGAMES_DIR = SAVE_APP / "RSDragonwilds" / "Saved" / "SaveGames"

BACKUP_QUIET_SECONDS = 5     # saves must be untouched this long before a backup starts
BACKUP_QUIET_TIMEOUT = 60    # give up waiting for a quiet moment after this long
BACKUP_COPY_ATTEMPTS = 3     # tries per file if it is locked or changes mid-copy
BACKUP_RETRY_DELAY = 1.0
PARTIAL_BACKUP_SUFFIX = ".partial"


# ──────────────────────────────────────────────────────────────────────────────
# SteamCMD
# ──────────────────────────────────────────────────────────────────────────────

def steamcmd_executable(steamcmd_dir: Path) -> Path:
    return steamcmd_dir / ("steamcmd.sh" if IS_LINUX else "steamcmd.exe")


def download_steamcmd(steamcmd_dir: Path, log, progress_cb=None) -> bool:
    log("Downloading SteamCMD...")
    steamcmd_dir.mkdir(parents=True, exist_ok=True)
    is_linux = sys.platform.startswith("linux")
    archive_path = steamcmd_dir / ("steamcmd_linux.tar.gz" if is_linux else "steamcmd.zip")
    url = STEAM_CMD_URL_LINUX if is_linux else STEAM_CMD_URL_WINDOWS
    try:
        def _reporthook(block, block_size, total):
            if progress_cb and total > 0:
                progress_cb(block * block_size, total)

        urllib.request.urlretrieve(url, archive_path, _reporthook)
        log("Extracting SteamCMD...")
        if is_linux:
            with tarfile.open(archive_path, "r:gz") as archive:
                archive.extractall(steamcmd_dir, filter="data")
        else:
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(steamcmd_dir)
        archive_path.unlink(missing_ok=True)
        log(f"SteamCMD ready at {steamcmd_dir}", "OK")
        return True
    except Exception as exc:
        log(f"SteamCMD download failed: {exc}", "ERROR")
        return False


def install_server(install_dir: Path, steamcmd_dir: Path, log) -> bool:
    exe = steamcmd_executable(steamcmd_dir)
    if not exe.exists():
        log(f"{exe.name} not found.", "ERROR")
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
    """Find a supported server launcher or binary beneath the install directory."""
    # On Linux the supported launch target is the RSDragonwildsServer.sh script in the
    # install root; it starts the shipping binary with the arguments it needs.
    names = (["RSDragonwildsServer.sh", "RSDragonwildsServer-Linux-Shipping",
              "RSDragonwildsServer", "RSDragonwildsServer.exe"]
             if IS_LINUX else ["RSDragonwildsServer.exe"])
    roots = [
        install_dir / "steamcmd" / "steamapps" / "common" / STEAM_APP_DIR,
        install_dir,
        install_dir / "steamapps" / "common" / STEAM_APP_DIR,
    ]
    for name in names:
        for root in roots:
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
        try:
            for match in install_dir.rglob(name):
                if match.is_file():
                    return str(match)
        except OSError:
            break

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

    # Refuse obviously dangerous targets: a drive root, the home folder, or anything above it.
    home = Path.home().resolve()
    if target == Path(target.anchor) or target == home or target in home.parents:
        log(f"Refusing to delete unsafe path: {target}", "ERROR")
        return False

    # Only delete folders that are empty or actually hold a server install.
    try:
        is_empty = not any(target.iterdir())
    except OSError as exc:
        log(f"Could not inspect install directory: {exc}", "ERROR")
        return False
    if not is_empty and not _looks_like_server_install(target):
        log(
            f"Refusing to delete {target}: no steamcmd folder or server executable was found in it.",
            "ERROR",
        )
        return False

    try:
        log(f"Deleting server files from {target}...", "WARN")
        shutil.rmtree(target)
        log("Server files deleted.", "OK")
        return True
    except Exception as exc:
        log(f"Failed to delete server files: {exc}", "ERROR")
        return False


def _looks_like_server_install(path: Path) -> bool:
    return (
        (path / "steamcmd").is_dir()
        or (path / "steamapps").is_dir()
        or find_server_exe(path) is not None
    )


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

def server_root_from_exe(exe_path):
    """Return the server install root for a launcher or shipping binary path, or None.

    The launcher (RSDragonwildsServer.exe or RSDragonwildsServer.sh) sits in the root;
    the binary it starts lives in <root>/RSDragonwilds/Binaries/<Platform>/.
    """
    exe_path = str(exe_path or "").strip()
    if not exe_path:
        return None
    p = Path(exe_path)
    if not p.is_file():
        return None
    binaries_dir = p.parent.parent
    if (binaries_dir.name.lower() == "binaries"
            and binaries_dir.parent.name.lower() == "rsdragonwilds"):
        return binaries_dir.parent.parent
    return p.parent


def _dedicated_config_paths_from_exe(exe_path: str) -> list[Path]:
    base = server_root_from_exe(exe_path)
    if base is None:
        return []
    is_windows_exe = Path(str(exe_path).strip()).suffix.lower() == ".exe"
    config_platform = "WindowsServer" if is_windows_exe else CONFIG_PLATFORM
    paths = [base / "RSDragonwilds" / "Saved" / "Config" / config_platform / "DedicatedServer.ini"]
    if config_platform == "WindowsServer":
        paths.append(base / "Saved" / "Config" / config_platform / "DedicatedServer.ini")
    return paths


def dedicated_savegames_paths_from_exe(exe_path: str) -> list[Path]:
    base = server_root_from_exe(exe_path)
    if base is None:
        return []
    return [
        base / "RSDragonwilds" / "Saved" / "SaveGames",
        base / "Saved" / "SaveGames",
    ]


def dedicated_log_paths_from_exe(exe_path: str) -> list[Path]:
    base = server_root_from_exe(exe_path)
    if base is None:
        return []
    return [
        base / "RSDragonwilds" / "Saved" / "Logs" / "RSDragonwilds.log",
        base / "Saved" / "Logs" / "RSDragonwilds.log",
    ]


def backup_savegames(destination_root: Path, exe_path: str, log,
                     quiet_seconds: float = BACKUP_QUIET_SECONDS,
                     quiet_timeout: float = BACKUP_QUIET_TIMEOUT) -> bool:
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

    # The server may be mid-save; give it a moment to finish before copying.
    if not _wait_for_quiet_saves([src for _, src in sources], log, quiet_seconds, quiet_timeout):
        log("SaveGames are still being written -- backing up anyway and verifying each file.", "WARN")

    destination_root = Path(destination_root)
    staging_root = None
    try:
        destination_root.mkdir(parents=True, exist_ok=True)
        _remove_stale_partial_backups(destination_root)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_root = destination_root / f"DragonwildsBackup-{stamp}"
        if backup_root.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_root = destination_root / f"DragonwildsBackup-{stamp}"

        # Build the backup under a .partial name so an incomplete copy never looks finished.
        staging_root = destination_root / f"{backup_root.name}{PARTIAL_BACKUP_SUFFIX}"
        staging_root.mkdir()
        for label, src in sources:
            _copy_tree_stable(src, staging_root / label)
            log(f"Backed up {src} to {backup_root / label}", "OK")
        staging_root.rename(backup_root)
    except OSError as exc:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        log(f"SaveGames backup failed: {exc}", "ERROR")
        return False

    log(f"Backup complete: {backup_root}", "OK")
    return True


def _latest_mtime(root: Path) -> float:
    latest = 0.0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                latest = max(latest, (Path(dirpath) / name).stat().st_mtime)
            except OSError:
                continue
    return latest


def _wait_for_quiet_saves(sources: list[Path], log, quiet_seconds: float, timeout: float) -> bool:
    """Wait until no save file has been modified for `quiet_seconds`. False if it never settles."""
    if quiet_seconds <= 0:
        return True
    deadline = time.monotonic() + timeout
    announced = False
    while True:
        idle = time.time() - max(_latest_mtime(src) for src in sources)
        if idle >= quiet_seconds:
            return True
        if time.monotonic() >= deadline:
            return False
        if not announced:
            log("SaveGames were just written -- waiting for the server to finish saving...")
            announced = True
        time.sleep(1)


def _file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _copy_file_stable(src: Path, dest: Path) -> None:
    """Copy one file, retrying if it was locked or changed while being copied."""
    last_error = None
    for attempt in range(BACKUP_COPY_ATTEMPTS):
        if attempt:
            time.sleep(BACKUP_RETRY_DELAY)
        try:
            before = _file_signature(src)
            shutil.copy2(src, dest)
            if _file_signature(src) == before:
                return
            last_error = None
        except FileNotFoundError:
            # The server removed the file (e.g. a temp file); nothing left to back up.
            dest.unlink(missing_ok=True)
            return
        except OSError as exc:
            last_error = exc
    reason = last_error or "it kept changing while being copied"
    raise OSError(f"could not get a clean copy of {src}: {reason}")


def _copy_tree_stable(src: Path, dest: Path) -> None:
    for dirpath, _dirnames, filenames in os.walk(src):
        target_dir = dest / Path(dirpath).relative_to(src)
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            _copy_file_stable(Path(dirpath) / name, target_dir / name)


def _remove_stale_partial_backups(destination_root: Path) -> None:
    """Clear staging folders left behind by a backup that was interrupted."""
    cutoff = time.time() - 3600
    for partial in destination_root.glob(f"DragonwildsBackup-*{PARTIAL_BACKUP_SUFFIX}"):
        try:
            if partial.is_dir() and partial.stat().st_mtime < cutoff:
                shutil.rmtree(partial, ignore_errors=True)
        except OSError:
            continue


def prune_savegame_backups(destination_root: Path, retention_days: int, log,
                           keep_latest: int = 3) -> int:
    """Delete expired backups, always keeping the newest `keep_latest` regardless of age."""
    if retention_days < 1 or not destination_root.is_dir():
        return 0

    backups: list[tuple[datetime, Path]] = []
    for backup_root in destination_root.glob("DragonwildsBackup-*"):
        if not backup_root.is_dir():
            continue
        try:
            stamp = backup_root.name.removeprefix("DragonwildsBackup-")
            try:
                created_at = datetime.strptime(stamp, "%Y%m%d-%H%M%S")
            except ValueError:
                created_at = datetime.strptime(stamp, "%Y%m%d-%H%M%S-%f")
        except ValueError:
            continue
        backups.append((created_at, backup_root))

    backups.sort(key=lambda item: item[0], reverse=True)
    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted = 0
    for created_at, backup_root in backups[max(keep_latest, 0):]:
        if created_at >= cutoff:
            continue
        try:
            shutil.rmtree(backup_root)
            log(f"Deleted expired backup: {backup_root}", "INFO")
            deleted += 1
        except OSError as exc:
            log(f"Could not delete expired backup {backup_root}: {exc}", "WARN")
    return deleted


def write_config(cfg: dict, log) -> bool:
    """Write DedicatedServer.ini. Returns False if there was nowhere to write it yet."""
    log("Writing DedicatedServer.ini...")
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

    written = False

    # Per-user config location (LocalAppData); not used on Linux.
    if CONFIG_FILE is not None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(content, encoding="utf-8")
        log(f"Config written to {CONFIG_FILE}", "OK")
        written = True

    # Locations under the server install tree, if applicable.
    for exe_cfg_path in _dedicated_config_paths_from_exe(cfg.get("server_exe", "")):
        exe_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        exe_cfg_path.write_text(content, encoding="utf-8")
        log(f"Config {'also ' if written else ''}written to {exe_cfg_path}", "OK")
        written = True

    if not written:
        log("Server files not found -- DedicatedServer.ini will be written once the "
            "server is installed or selected.", "WARN")
    return written


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
    if target is None or not target.exists():
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
    if IS_LINUX:
        if shutil.which("ufw"):
            log(f"Configuring UFW for UDP {port}...")
            for direction in ("in", "out"):
                port_spec = f"{port}/udp"
                result = subprocess.run(
                    ["ufw", "allow", direction, port_spec],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    log(f"UFW {direction} rule for UDP {port} created.", "OK")
                else:
                    log(f"Failed to create UFW {direction} rule: {result.stderr.strip()}", "ERROR")
            log("Firewall configured. Router UDP port forwarding may also be required.", "WARN")
            return
        if shutil.which("firewall-cmd"):
            log(f"Configuring firewalld for UDP {port}...")
            result = subprocess.run(
                ["firewall-cmd", "--permanent", f"--add-port={port}/udp"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                subprocess.run(["firewall-cmd", "--reload"], capture_output=True, text=True)
                log(f"firewalld opened UDP {port}.", "OK")
            else:
                log(f"Failed to configure firewalld: {result.stderr.strip()}", "ERROR")
            return
        log("No supported firewall tool found (ufw or firewall-cmd); configure UDP manually.", "WARN")
        return

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
