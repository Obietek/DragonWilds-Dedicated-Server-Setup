# Dragonwilds Server Manager

`DragonwildsManager.exe` is a Windows desktop app for installing, configuring, updating, launching, and monitoring a RuneScape: Dragonwilds dedicated server.

It is built from this project with PyInstaller and outputs a single executable at `dist\DragonwildsManager.exe`.

## What It Does

The app provides a simple GUI for common dedicated-server tasks:

- Install SteamCMD
- Download or update the Dragonwilds dedicated server files
- Edit and save `DedicatedServer.ini`
- Create Windows Firewall UDP rules
- Start and stop the dedicated server
- Monitor server status, PID, uptime, and live app log output
- Delete the configured server install folder

## Build Output

Run:

```powershell
python build.py
```

This creates:

```text
dist\DragonwildsManager.exe
```

The build script also installs the required Python packages:

- `psutil`
- `pyinstaller`

## Running The Exe

1. Build the project with `python build.py`.
2. Open the `dist` folder.
3. Run `DragonwildsManager.exe`.
4. For firewall changes, run it as Administrator.

The executable is built with `--noconsole`, so it launches as a normal Windows app without a terminal window.

## First-Time Setup

On first launch, use the tabs in this order:

1. `Config`
2. `Setup`
3. `Status`

### Config Tab

This tab manages your server settings.

Fields:

- `Player ID (Owner)`: required
- `Server Name`: required
- `Default World Name`: required
- `Admin Password`: required
- `World Password`: optional
- `Server Port`: defaults to `7777`

Buttons:

- `Save Configuration`: saves the values and writes `DedicatedServer.ini`
- `Reload from File`: reloads values from existing config files

The app writes config data to:

- `%LOCALAPPDATA%\RSDragonwilds\Saved\Config\WindowsServer\DedicatedServer.ini`
- `<server install>\RSDragonwilds\Saved\Config\WindowsServer\DedicatedServer.ini`
- `<server install>\Saved\Config\WindowsServer\DedicatedServer.ini`

## Setup Tab

This tab handles installation and maintenance.

Fields:

- `Install Folder`: where server files and SteamCMD will live
- `Existing Server Exe`: lets you point the app to an existing `RSDragonwildsServer.exe`

Buttons:

- `Full Setup`: downloads SteamCMD, installs server files, writes config, and applies firewall rules
- `Firewall Only`: creates Windows Firewall UDP allow rules for the configured port
- `Save Config Only`: writes config without reinstalling anything
- `Update Server Files`: updates the dedicated server through SteamCMD
- `Delete Server Files`: removes the configured install directory after confirmation

## Status Tab

This tab is used after setup is complete.

It shows:

- whether the server process is online or offline
- process ID
- uptime
- detected server executable path
- configured world name
- live application log messages

Buttons:

- `Start Server`: launches `RSDragonwildsServer.exe`
- `Stop Server`: terminates the detected server process
- `Open Server Folder`: opens the install folder in Windows Explorer

## How It Works

At startup, the app:

- loads saved app settings from `%APPDATA%\DragonwildsManager\settings.json`
- loads server config values from existing `DedicatedServer.ini` files
- restores the last window position
- starts a background monitor that watches for `RSDragonwildsServer.exe`

When you launch the server, the app:

- resolves the server executable path
- saves the current configuration
- writes `DedicatedServer.ini`
- starts the server process
- begins monitoring it for uptime and status changes

## Files And Paths

Important locations used by the app:

- App settings: `%APPDATA%\DragonwildsManager\settings.json`
- Local config: `%LOCALAPPDATA%\RSDragonwilds\Saved\Config\WindowsServer\DedicatedServer.ini`
- Built exe: `dist\DragonwildsManager.exe`
- Default install folder: `%USERPROFILE%\DragonWildsServer`

## Notes

- Firewall configuration may fail unless the app is run as Administrator.
- SteamCMD installation and updates can take several minutes.
- The delete option permanently removes the configured install directory.
- If you already have a server installed, use the `Existing Server Exe` field instead of reinstalling.

## Development

Run from source:

```powershell
python main.py
```

Build the executable:

```powershell
python build.py
```

## GitHub Releases

The repo includes a GitHub Actions workflow at `.github/workflows/release.yml`.

It will:

- build `dist\DragonwildsManager.exe` on Windows
- upload the executable as a workflow artifact
- attach the executable to a GitHub Release when you push a tag like `v1.0.0`

To publish a release from GitHub:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

You can also run the workflow manually from the GitHub Actions tab to generate a downloadable build artifact without creating a release.

## Release Signing

`build.py` can automatically sign `dist\DragonwildsManager.exe` when signing credentials are provided through environment variables.

Supported variables:

- `SIGNTOOL_PATH`: optional full path to `signtool.exe`
- `CODESIGN_CERT_SHA1`: thumbprint of a code-signing certificate in the Windows certificate store
- `CODESIGN_PFX_PATH`: path to a `.pfx` code-signing certificate file
- `CODESIGN_PFX_PASSWORD`: password for the `.pfx` file
- `CODESIGN_TIMESTAMP_URL`: optional timestamp URL override

Use either `CODESIGN_CERT_SHA1` or `CODESIGN_PFX_PATH`.

Example using a certificate already installed in Windows:

```powershell
$env:CODESIGN_CERT_SHA1="YOUR_CERT_THUMBPRINT"
python build.py
```

Example using a `.pfx` file:

```powershell
$env:CODESIGN_PFX_PATH="C:\certs\codesign.pfx"
$env:CODESIGN_PFX_PASSWORD="your-password"
python build.py
```

If no signing variables are set, the build still succeeds, but the executable will be left unsigned.
