import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import installer, monitor


class LinuxSupportTests(unittest.TestCase):

    def test_uses_linux_steamcmd_script(self):
        with patch.object(installer, "IS_LINUX", True):
            path = installer.steamcmd_executable(Path("server"))

        self.assertEqual(path, Path("server") / "steamcmd.sh")

    def test_finds_linux_server_binary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "Binaries" / "Linux" / "RSDragonwildsServer-Linux-Shipping"
            binary.parent.mkdir(parents=True)
            binary.touch()

            with patch.object(installer, "IS_LINUX", True):
                found = installer.find_server_exe(root)

        self.assertEqual(found, str(binary))

    def test_linux_executable_config_path_uses_linux_server_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "RSDragonwildsServer"
            executable.touch()

            with patch.object(installer, "CONFIG_PLATFORM", "LinuxServer"):
                paths = installer._dedicated_config_paths_from_exe(str(executable))

        self.assertTrue(all("LinuxServer" in str(path) for path in paths))

    def test_ufw_receives_port_as_a_separate_argument(self):
        result = SimpleNamespace(returncode=0, stderr="")
        with (
            patch.object(installer, "IS_LINUX", True),
            patch.object(installer.shutil, "which", return_value="/usr/sbin/ufw"),
            patch.object(installer.subprocess, "run", return_value=result) as run,
        ):
            installer.set_firewall(7777, lambda *_args: None)

        self.assertEqual(
            run.call_args_list[0].args[0],
            ["ufw", "allow", "in", "7777/udp"],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            ["ufw", "allow", "out", "7777/udp"],
        )

    def test_monitor_detects_linux_server_process_name(self):
        process = SimpleNamespace(info={
            "pid": 12345,
            "name": "RSDragonwildsServer-Linux-Shipping",
            "exe": "/srv/dragonwilds/RSDragonwildsServer-Linux-Shipping",
            "create_time": 1,
        })
        server_monitor = monitor.ServerMonitor()

        with patch.object(monitor.psutil, "process_iter", return_value=[process]):
            server_monitor._poll()

        self.assertTrue(server_monitor.is_online)
        self.assertEqual(server_monitor.pid, 12345)


def _make_linux_install(root: Path) -> tuple[Path, Path]:
    """Create the layout Steam installs on Linux; returns (launcher script, shipping binary)."""
    script = root / "RSDragonwildsServer.sh"
    binary = root / "RSDragonwilds" / "Binaries" / "Linux" / "RSDragonwildsServer-Linux-Shipping"
    binary.parent.mkdir(parents=True)
    script.touch()
    binary.touch()
    return script, binary


class LinuxInstallLayoutTests(unittest.TestCase):

    def test_prefers_launcher_script_over_shipping_binary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script, _binary = _make_linux_install(root)

            with patch.object(installer, "IS_LINUX", True):
                found = installer.find_server_exe(root)

        self.assertEqual(found, str(script))

    def test_server_root_is_the_same_for_script_and_shipping_binary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script, binary = _make_linux_install(root)

            self.assertEqual(installer.server_root_from_exe(str(script)), root)
            self.assertEqual(installer.server_root_from_exe(str(binary)), root)
            self.assertIsNone(installer.server_root_from_exe(str(root / "missing")))
            self.assertIsNone(installer.server_root_from_exe(""))

    def test_paths_from_shipping_binary_use_install_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _script, binary = _make_linux_install(root)
            saved = root / "RSDragonwilds" / "Saved"

            with patch.object(installer, "CONFIG_PLATFORM", "LinuxServer"):
                config_paths = installer._dedicated_config_paths_from_exe(str(binary))
            save_paths = installer.dedicated_savegames_paths_from_exe(str(binary))
            log_paths = installer.dedicated_log_paths_from_exe(str(binary))

        self.assertEqual(config_paths, [saved / "Config" / "LinuxServer" / "DedicatedServer.ini"])
        self.assertEqual(save_paths[0], saved / "SaveGames")
        self.assertEqual(log_paths[0], saved / "Logs" / "RSDragonwilds.log")

    def test_config_is_written_only_inside_install_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = Path(temp_dir) / "server"
            server.mkdir()
            script, _binary = _make_linux_install(server)

            with (
                patch.object(installer, "CONFIG_PLATFORM", "LinuxServer"),
                patch.object(installer, "CONFIG_DIR", None),
                patch.object(installer, "CONFIG_FILE", None),
                patch.object(installer, "SAVEGAMES_DIR", Path(temp_dir) / "local-saves"),
            ):
                written = installer.write_config(
                    {"server_exe": str(script), "owner_id": "owner-1"}, lambda *_args: None
                )

            ini = server / "RSDragonwilds" / "Saved" / "Config" / "LinuxServer" / "DedicatedServer.ini"
            self.assertTrue(written)
            self.assertIn("OwnerId=owner-1", ini.read_text(encoding="utf-8"))
            self.assertEqual(sorted(path.name for path in server.iterdir()),
                             ["RSDragonwilds", "RSDragonwildsServer.sh"])

    def test_config_write_reports_when_server_is_not_installed(self):
        messages = []
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(installer, "CONFIG_DIR", None),
                patch.object(installer, "CONFIG_FILE", None),
                patch.object(installer, "SAVEGAMES_DIR", Path(temp_dir) / "local-saves"),
            ):
                written = installer.write_config(
                    {"server_exe": ""}, lambda message, level="INFO": messages.append(level)
                )
                defaults = installer.read_config()

        self.assertFalse(written)
        self.assertEqual(messages[-1], "WARN")
        self.assertEqual(defaults["port"], "7777")

    def test_monitor_reads_log_from_install_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _script, binary = _make_linux_install(root)
            log = root / "RSDragonwilds" / "Saved" / "Logs" / "RSDragonwilds.log"
            log.parent.mkdir(parents=True)
            log.write_text("LogNet: Join succeeded: Alice\n", encoding="utf-8")
            process = SimpleNamespace(info={
                "pid": 12345,
                "name": binary.name,
                "exe": str(binary),
                "create_time": 1,
            })
            server_monitor = monitor.ServerMonitor()

            with patch.object(monitor.psutil, "process_iter", return_value=[process]):
                server_monitor._poll()

        self.assertEqual(server_monitor.players, {"Alice"})

    def test_monitor_uses_first_argument_when_run_through_emulator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _script, binary = _make_linux_install(Path(temp_dir))
            process = SimpleNamespace(
                info={
                    "pid": 12345,
                    "name": binary.name,
                    "exe": "/usr/bin/FEXInterpreter",
                    "create_time": 1,
                },
                cmdline=lambda: [str(binary), "RSDragonwilds", "-log"],
            )
            server_monitor = monitor.ServerMonitor()

            with patch.object(monitor.psutil, "process_iter", return_value=[process]):
                server_monitor._poll()

        self.assertTrue(server_monitor.is_online)
        self.assertEqual(server_monitor.exe_path, str(binary))

    def test_monitor_leaves_path_blank_when_binary_is_not_identifiable(self):
        process = SimpleNamespace(
            info={
                "pid": 12345,
                "name": "RSDragonwildsServer.exe",
                "exe": "/usr/bin/wine64-preloader",
                "create_time": 1,
            },
            cmdline=lambda: ["Z:\\srv\\dragonwilds\\RSDragonwildsServer.exe", "-log"],
        )
        server_monitor = monitor.ServerMonitor()

        with patch.object(monitor.psutil, "process_iter", return_value=[process]):
            server_monitor._poll()

        self.assertTrue(server_monitor.is_online)
        self.assertEqual(server_monitor.exe_path, "")


if __name__ == "__main__":
    unittest.main()