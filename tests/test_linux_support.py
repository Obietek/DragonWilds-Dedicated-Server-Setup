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


if __name__ == "__main__":
    unittest.main()