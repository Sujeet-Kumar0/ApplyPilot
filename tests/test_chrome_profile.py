"""Tests for Chrome profile setup and Preferences patching.

Regression test for: extensions.settings being wiped by _suppress_restore_nag(),
which caused manually-installed extensions (ApplyPilot) to disappear on every
Chrome restart.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestSuppressRestoreNag(unittest.TestCase):
    """_suppress_restore_nag() must patch preferences without destroying extension state."""

    def _make_prefs(self, extra: dict | None = None) -> tuple[Path, Path]:
        """Write a minimal Preferences file to a temp dir. Returns (profile_dir, prefs_file)."""
        tmp = tempfile.mkdtemp()
        profile_dir = Path(tmp)
        default_dir = profile_dir / "Default"
        default_dir.mkdir()
        prefs = {
            "profile": {"exit_type": "Crashed"},
            "session": {"restore_on_startup": 1},
        }
        if extra:
            prefs.update(extra)
        prefs_file = default_dir / "Preferences"
        prefs_file.write_text(json.dumps(prefs), encoding="utf-8")
        return profile_dir, prefs_file

    def _read_prefs(self, prefs_file: Path) -> dict:
        return json.loads(prefs_file.read_text(encoding="utf-8"))

    def test_removes_in_profile_extension_entries(self):
        """Web-store extensions (path inside Default/Extensions/) are removed.

        Chrome re-downloads extensions that still have entries in extensions.settings
        even after their files are deleted.  We must remove those entries.
        """
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        profile_dir = tmp
        default_dir = profile_dir / "Default"
        default_dir.mkdir()

        in_profile_path = str(default_dir / "Extensions" / "momentumextensionid00000000000")
        external_path = "/home/user/.applypilot/chrome-workers/extensions/worker-0"

        prefs = {
            "profile": {"exit_type": "Normal"},
            "session": {"restore_on_startup": 1},
            "extensions": {
                "settings": {
                    "momentumextensionid00000000000": {
                        "path": in_profile_path,
                        "state": 1,
                    },
                    "applypilotextensionid000000000": {
                        "path": external_path,
                        "state": 1,
                        "toolbar_pin": 1,
                    },
                }
            },
        }
        prefs_file = default_dir / "Preferences"
        prefs_file.write_text(json.dumps(prefs), encoding="utf-8")

        from applypilot.apply.chrome import _suppress_restore_nag
        _suppress_restore_nag(profile_dir)

        result = self._read_prefs(prefs_file)
        settings = result.get("extensions", {}).get("settings", {})

        self.assertNotIn(
            "momentumextensionid00000000000", settings,
            "In-profile web-store extension should be removed",
        )
        self.assertIn(
            "applypilotextensionid000000000", settings,
            "External --load-extension entry should be preserved",
        )
        self.assertEqual(
            settings["applypilotextensionid000000000"]["toolbar_pin"], 1,
            "Pin state should survive restart",
        )

    def test_enables_developer_mode(self):
        """Developer mode is set to True so --load-extension works."""
        profile_dir, prefs_file = self._make_prefs()
        from applypilot.apply.chrome import _suppress_restore_nag
        _suppress_restore_nag(profile_dir)
        result = self._read_prefs(prefs_file)
        self.assertTrue(result["extensions"]["ui"]["developer_mode"])

    def test_sets_new_tab_on_startup_without_worker_id(self):
        """Without worker_id, restore_on_startup=5 (New Tab page)."""
        profile_dir, prefs_file = self._make_prefs()
        from applypilot.apply.chrome import _suppress_restore_nag
        _suppress_restore_nag(profile_dir)
        result = self._read_prefs(prefs_file)
        self.assertEqual(result["session"]["restore_on_startup"], 5)
        self.assertNotIn("startup_urls", result["session"])

    def test_sets_startup_url_with_worker_id(self):
        """With worker_id=2, restore_on_startup=4 and startup_urls points to the worker server."""
        profile_dir, prefs_file = self._make_prefs()
        from applypilot.apply.chrome import _suppress_restore_nag
        _suppress_restore_nag(profile_dir, worker_id=2)
        result = self._read_prefs(prefs_file)
        self.assertEqual(result["session"]["restore_on_startup"], 4,
                         "Expected 4 (specific URLs) when worker_id is provided")
        self.assertEqual(result["session"]["startup_urls"], ["http://localhost:7382/"],
                         "startup_urls should point to port 7380+worker_id")

    def test_suppresses_crash_restore(self):
        """exit_type is reset to Normal to prevent the restore-session nag."""
        profile_dir, prefs_file = self._make_prefs()
        from applypilot.apply.chrome import _suppress_restore_nag
        _suppress_restore_nag(profile_dir)
        result = self._read_prefs(prefs_file)
        self.assertEqual(result["profile"]["exit_type"], "Normal")

    def test_disables_sync(self):
        """Google sync is disabled to prevent extension contamination."""
        profile_dir, prefs_file = self._make_prefs()
        from applypilot.apply.chrome import _suppress_restore_nag
        _suppress_restore_nag(profile_dir)
        result = self._read_prefs(prefs_file)
        self.assertFalse(result["sync"]["requested"])
        self.assertFalse(result["signin"]["allowed"])

    def test_no_op_when_prefs_missing(self):
        """No exception when Preferences file doesn't exist yet."""
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        from applypilot.apply.chrome import _suppress_restore_nag
        _suppress_restore_nag(tmp)  # should not raise


class TestSetupWorkerProfileExtensionWipe(unittest.TestCase):
    """setup_worker_profile() wipes the entire in-profile Extensions directory.

    Our extension loads via --load-extension (outside user-data-dir), so nothing
    in Default/Extensions/ is needed.  All extensions are wiped to prevent
    Chrome from re-downloading legacy extensions (Momentum, Tampermonkey, etc.).
    """

    def _plant_extension(self, profile_dir: Path, ext_id: str,
                         version: str, name: str) -> Path:
        """Create a fake extension at Default/Extensions/{ext_id}/{version}_0/."""
        ext_ver_dir = profile_dir / "Default" / "Extensions" / ext_id / f"{version}_0"
        ext_ver_dir.mkdir(parents=True)
        manifest = {"name": name, "version": version, "manifest_version": 3}
        (ext_ver_dir / "manifest.json").write_text(json.dumps(manifest))
        return ext_ver_dir

    def test_wipes_all_extension_files(self):
        """ALL extensions (including ApplyPilot) are removed from the in-profile dir.

        Our extension is loaded via --load-extension from outside the profile.
        """
        import tempfile
        from unittest.mock import patch

        tmp = Path(tempfile.mkdtemp())
        worker_dir = tmp / "worker-99"
        self._plant_extension(worker_dir, "momentumextensionid00000000000000", "5.0", "Momentum")
        self._plant_extension(
            worker_dir, "applypilotextensionid0000000000000", "2.0", "ApplyPilot Control Panel"
        )

        with (
            patch("applypilot.config.CHROME_WORKER_DIR", tmp),
            patch("applypilot.apply.chrome._suppress_restore_nag"),
            patch("applypilot.apply.chrome._remove_singleton_locks"),
            patch("applypilot.apply.chrome.shutil.copytree"),
        ):
            prefs_file = worker_dir / "Default" / "Preferences"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("{}")

            from applypilot.apply.chrome import setup_worker_profile
            setup_worker_profile(99)

        ext_dir = worker_dir / "Default" / "Extensions"
        # Directory should exist but be empty
        self.assertTrue(ext_dir.exists(), "Extensions dir should be recreated")
        remaining = list(ext_dir.iterdir())
        self.assertEqual(remaining, [], f"Extensions dir should be empty, found: {remaining}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
