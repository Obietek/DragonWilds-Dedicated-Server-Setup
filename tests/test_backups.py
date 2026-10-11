import tempfile
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
                ok = installer.backup_savegames(destination, "", lambda *_args: None)

            copies = list(destination.glob("DragonwildsBackup-*/LocalSaveGames/world.sav"))
            self.assertTrue(ok)
            self.assertEqual(len(copies), 1)
            self.assertEqual(copies[0].read_text(encoding="utf-8"), "world data")

    def test_backup_without_savegames_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "backups"

            with patch.object(installer, "SAVEGAMES_DIR", root / "missing"):
                ok = installer.backup_savegames(destination, "", lambda *_args: None)

            self.assertFalse(ok)
            self.assertFalse(destination.exists())

    def test_prunes_only_expired_backup_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expired = root / "DragonwildsBackup-20000101-000000"
            recent = root / f"DragonwildsBackup-{datetime.now():%Y%m%d-%H%M%S}"
            unrelated = root / "keep-this-folder"
            for folder in (expired, recent, unrelated):
                folder.mkdir()

            deleted = installer.prune_savegame_backups(root, 7, lambda *_args: None)

            self.assertEqual(deleted, 1)
            self.assertFalse(expired.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
