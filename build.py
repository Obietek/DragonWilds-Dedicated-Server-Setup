"""
build.py
Run this once to produce dist/DragonwildsManager.exe

Requirements:
    pip install pyinstaller psutil

Usage:
    python build.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"


def _find_signtool() -> str | None:
    configured = os.getenv("SIGNTOOL_PATH", "").strip()
    if configured:
        return configured
    return shutil.which("signtool")


def _sign_exe(exe_path: Path) -> bool:
    signtool = _find_signtool()
    thumbprint = os.getenv("CODESIGN_CERT_SHA1", "").strip()
    pfx_path = os.getenv("CODESIGN_PFX_PATH", "").strip()
    pfx_password = os.getenv("CODESIGN_PFX_PASSWORD", "")
    timestamp_url = os.getenv("CODESIGN_TIMESTAMP_URL", DEFAULT_TIMESTAMP_URL).strip()

    if not thumbprint and not pfx_path:
        print("\n[3/3] Skipping code signing (no certificate configured).")
        print("Set CODESIGN_CERT_SHA1 or CODESIGN_PFX_PATH to sign release builds automatically.")
        return True

    if not signtool:
        print("\n[3/3] Code signing requested, but signtool was not found.", file=sys.stderr)
        print("Set SIGNTOOL_PATH or run from a developer shell with signtool available.", file=sys.stderr)
        return False

    print("\n[3/3] Signing executable...")
    cmd = [
        signtool,
        "sign",
        "/fd", "SHA256",
        "/tr", timestamp_url,
        "/td", "SHA256",
    ]

    if thumbprint:
        cmd.extend(["/sha1", thumbprint])
    else:
        cmd.extend(["/f", pfx_path])
        if pfx_password:
            cmd.extend(["/p", pfx_password])

    cmd.append(str(exe_path))

    result = subprocess.run(cmd, cwd=str(HERE))
    if result.returncode != 0:
        print("Signing failed -- check the output above for errors.", file=sys.stderr)
        return False

    verify = subprocess.run(
        [signtool, "verify", "/pa", str(exe_path)],
        cwd=str(HERE),
    )
    if verify.returncode != 0:
        print("Signature verification failed after signing.", file=sys.stderr)
        return False

    print("Signing complete and verified.")
    return True


def main():
    print("=" * 60)
    print("  Dragonwilds Server Manager -- Build Script")
    print("=" * 60)

    # Install dependencies first
    print("\n[1/3] Installing dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "psutil", "pyinstaller", "--quiet"],
        check=True,
    )

    # PyInstaller command
    print("\n[2/3] Building executable with PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                          # single exe
        "--noconsole",                        # no console window
        "--name", "DragonwildsManager",
        "--add-data", f"{HERE / 'core'};core",  # bundle core package
        str(HERE / "main.py"),
    ]

    result = subprocess.run(cmd, cwd=str(HERE))

    if result.returncode == 0:
        exe_path = HERE / "dist" / "DragonwildsManager.exe"
        if not _sign_exe(exe_path):
            sys.exit(1)

        print("\n" + "=" * 60)
        print("  BUILD SUCCESSFUL!")
        print(f"  Exe: {exe_path}")
        print("=" * 60)
        print("\nTo install:")
        print("  1. Copy DragonwildsManager.exe anywhere you like")
        print("     (e.g. C:\\Program Files\\DragonwildsManager\\)")
        print("  2. Right-click -> Create shortcut -> drag to Desktop")
        print("  3. Always run as Administrator for firewall features")
        print("\nOptional signing environment variables:")
        print("  SIGNTOOL_PATH           Path to signtool.exe")
        print("  CODESIGN_CERT_SHA1      Thumbprint of a cert in the Windows cert store")
        print("  CODESIGN_PFX_PATH       Path to a .pfx file")
        print("  CODESIGN_PFX_PASSWORD   Password for the .pfx file")
        print(f"  CODESIGN_TIMESTAMP_URL  RFC 3161 timestamp URL (default: {DEFAULT_TIMESTAMP_URL})")
        print()
    else:
        print("\nBUILD FAILED -- check the output above for errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
