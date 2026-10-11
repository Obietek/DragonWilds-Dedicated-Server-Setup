import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core import installer


class BackupTests(unittest.TestCase):
    def test_backup_copies_savegames_into_timestamped_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saves = root / "saves"
            saves.mkdir()
            (saves / "world.sav").write_text("world data", encoding="utf-8")
            destination = root / "backups"

            with patch.object(installer, "SAVEGAMES_DIR", saves):
                ok = installer.backup_savegames(
                    destination, "", lambda *_args: None, quiet_seconds=0
                )

            copies = list(destination.glob("DragonwildsBackup-*/LocalSaveGames/world.sav"))
            self.assertTrue(ok)
            self.assertEqual(len(copies), 1)
            self.assertEqual(copies[0].read_text(encoding="utf-8"), "world data")

    def test_backup_without_savegames_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "backups"

            with patch.object(installer, "SAVEGAMES_DIR", root / "missing"):
                ok = installer.backup_savegames(
                    destination, "", lambda *_args: None, quiet_seconds=0
                )

            self.assertFalse(ok)
            self.assertFalse(destination.exists())

    def test_backup_recopies_file_that_changed_during_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saves = root / "saves"
            saves.mkdir()
            world = saves / "world.sav"
            world.write_text("old", encoding="utf-8")
            destination = root / "backups"
            real_copy = shutil.copy2
            calls = []

            def copy_then_modify(src, dest):
                real_copy(src, dest)
                calls.append(src)
                if len(calls) == 1:
                    world.write_text("new world data", encoding="utf-8")

            with (
                patch.object(installer, "SAVEGAMES_DIR", saves),
                patch.object(installer.shutil, "copy2", side_effect=copy_then_modify),
                patch.object(installer.time, "sleep"),
            ):
                ok = installer.backup_savegames(
                    destination, "", lambda *_args: None, quiet_seconds=0
                )

            copies = list(destination.glob("DragonwildsBackup-*/LocalSaveGames/world.sav"))
            self.assertTrue(ok)
            self.assertEqual(len(calls), 2)
            self.assertEqual(copies[0].read_text(encoding="utf-8"), "new world data")

    def test_backup_fails_cleanly_when_file_never_stops_changing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saves = root / "saves"
            saves.mkdir()
            world = saves / "world.sav"
            world.write_text("0", encoding="utf-8")
            destination = root / "backups"
            real_copy = shutil.copy2

            def copy_then_modify(src, dest):
                real_copy(src, dest)
                world.write_text(world.read_text(encoding="utf-8") + "x", encoding="utf-8")

            with (
                patch.object(installer, "SAVEGAMES_DIR", saves),
                patch.object(installer.shutil, "copy2", side_effect=copy_then_modify),
                patch.object(installer.time, "sleep"),
            ):
                ok = installer.backup_savegames(
                    destination, "", lambda *_args: None, quiet_seconds=0
                )

            self.assertFalse(ok)
            self.assertEqual(list(destination.iterdir()), [])

    def test_backup_waits_for_saves_to_go_quiet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            saves = Path(temp_dir) / "saves"
            saves.mkdir()
            world = saves / "world.sav"
            world.write_text("world data", encoding="utf-8")

            def finish_saving(_seconds):
                old = time.time() - 60
                os.utime(world, (old, old))

            with patch.object(installer.time, "sleep", side_effect=finish_saving) as sleep:
                quiet = installer._wait_for_quiet_saves([saves], lambda *_args: None, 5, 60)

            self.assertTrue(quiet)
            sleep.assert_called_once()

    def test_prunes_only_expired_backup_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expired = root / "DragonwildsBackup-20000101-000000"
            recent = root / f"DragonwildsBackup-{datetime.now():%Y%m%d-%H%M%S}"
            unrelated = root / "keep-this-folder"
            for folder in (expired, recent, unrelated):
                folder.mkdir()

            deleted = installer.prune_savegame_backups(
                root, 7, lambda *_args: None, keep_latest=1
            )

            self.assertEqual(deleted, 1)
            self.assertFalse(expired.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())

    def test_prune_keeps_newest_backups_even_when_all_are_expired(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folders = [root / f"DragonwildsBackup-2000010{day}-000000" for day in range(1, 6)]
            for folder in folders:
                folder.mkdir()

            deleted = installer.prune_savegame_backups(root, 7, lambda *_args: None)

            self.assertEqual(deleted, 2)
            self.assertEqual([folder.exists() for folder in folders],
                             [False, False, True, True, True])


class DeleteServerFilesTests(unittest.TestCase):
    def test_refuses_home_folder_and_its_parents(self):
        home = Path.home().resolve()
        with patch.object(installer.shutil, "rmtree") as rmtree:
            for target in (home, home.parent, Path(home.anchor)):
                self.assertFalse(installer.delete_server_files(target, lambda *_args: None))

        rmtree.assert_not_called()

    def test_refuses_folder_that_is_not_a_server_install(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "documents"
            root.mkdir()
            (root / "notes.txt").write_text("keep me", encoding="utf-8")

            ok = installer.delete_server_files(root, lambda *_args: None)

            self.assertFalse(ok)
            self.assertTrue((root / "notes.txt").exists())

    def test_deletes_folder_containing_steamcmd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "server"
            (root / "steamcmd").mkdir(parents=True)

            ok = installer.delete_server_files(root, lambda *_args: None)

            self.assertTrue(ok)
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
