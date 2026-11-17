"""Tests for check_chatgpt_plugin.py: the real package passes, broken copies fail."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_chatgpt_plugin as checker  # noqa: E402

PACKAGE = Path(__file__).resolve().parents[2] / "chatgpt"


class CheckChatGPTPlugin(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "chatgpt"
        shutil.copytree(PACKAGE, self.root)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def manifest(self) -> dict:
        return json.loads((self.root / "plugin.json").read_text())

    def write(self, m: dict) -> None:
        (self.root / "plugin.json").write_text(json.dumps(m))

    def test_package_passes(self) -> None:
        self.assertEqual(checker.check(PACKAGE), [])

    def test_zip_has_plugin_at_root(self) -> None:
        out = self.tmp / "p.zip"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(checker.main([str(self.root), "--zip", str(out)]), 0)
        names = zipfile.ZipFile(out).namelist()
        self.assertIn("plugin.json", names)
        self.assertIn("skills/prized-boxes/SKILL.md", names)
        self.assertIn("assets/icon.png", names)
        self.assertNotIn("README.md", names)

    def test_listing_limits(self) -> None:
        m = self.manifest()
        m["extensions"]["com.openai"]["interface"]["shortDescription"] = "Cloud dev boxes for coding agents"
        self.write(m)
        self.assertTrue(any("shortDescription" in p for p in checker.check(self.root)))

    def test_desktop_only_flag_required(self) -> None:
        m = self.manifest()
        del m["extensions"]["com.openai"]["requires_local_executor"]
        self.write(m)
        self.assertTrue(any("requires_local_executor" in p for p in checker.check(self.root)))

    def test_root_key_outside_schema(self) -> None:
        m = self.manifest()
        m["skills"] = "./skills/"
        self.write(m)
        self.assertTrue(any("skills: not allowed at the root" in p for p in checker.check(self.root)))

    def test_price_in_listing(self) -> None:
        m = self.manifest()
        m["extensions"]["com.openai"]["interface"]["longDescription"] += " From $10 a month."
        self.write(m)
        self.assertTrue(any("prices" in p for p in checker.check(self.root)))

    def test_skill_mentions_claude(self) -> None:
        skill = self.root / "skills" / "prized-boxes" / "SKILL.md"
        skill.write_text(skill.read_text() + "\nCopy Claude Code's sign-in too.\n")
        self.assertTrue(any("Claude" in p for p in checker.check(self.root)))

    def test_hooks_rejected(self) -> None:
        (self.root / "hooks").mkdir()
        self.assertTrue(any(p.startswith("hooks") for p in checker.check(self.root)))


if __name__ == "__main__":
    unittest.main()
