"""Tests for sync_skill.py, offline: prized.dev is faked.

  python3 -m unittest discover -s .github/scripts
"""
from __future__ import annotations

import contextlib
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import sync_skill  # noqa: E402

SKILL_MD = b"---\nname: demo\ndescription: A demo skill.\n---\n\n# Demo\n"


def archive(files: dict[str, bytes], symlink: str | None = None) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if symlink:
            info = tarfile.TarInfo(symlink)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
    return gzip.compress(raw.getvalue())


def site(files: dict[str, bytes], digest: str | None = None, symlink: str | None = None):
    """A fake fetch serving one skill named demo."""
    data = archive(files, symlink)
    index = {
        "$schema": sync_skill.SCHEMA,
        "skills": [
            {
                "name": "demo",
                "type": "archive",
                "description": "A demo skill.",
                "url": "/skills/demo.tar.gz",
                "digest": digest or "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        ],
    }

    def fetch(url: str, limit: int) -> bytes:
        if url.endswith("/.well-known/agent-skills/index.json"):
            return json.dumps(index).encode()
        if url == "https://prized.dev/skills/demo.tar.gz":
            return data
        raise AssertionError(url)

    return mock.patch.object(sync_skill, "fetch", fetch)


class SyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / ".claude-plugin").mkdir()
        (self.root / ".claude-plugin/plugin.json").write_text('{\n  "name": "x",\n  "version": "1.0.0"\n}\n')

    def run_sync(self, *args: str) -> int:
        argv = ["sync_skill.py", "--root", str(self.root), *args]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            code = sync_skill.main()
        self.output = out.getvalue()
        return code

    def version(self) -> str:
        return json.loads((self.root / ".claude-plugin/plugin.json").read_text())["version"]

    def test_first_sync_fills_without_bump_then_change_bumps(self) -> None:
        files = {"SKILL.md": SKILL_MD, "scripts/a.py": b"print(1)\n"}
        with site(files):
            self.assertEqual(self.run_sync(), 0)
        self.assertEqual((self.root / "skills/demo/scripts/a.py").read_bytes(), b"print(1)\n")
        self.assertEqual(self.version(), "1.0.0")
        with site(files):
            self.assertEqual(self.run_sync("--check"), 0)
            self.assertEqual(self.run_sync(), 0)
        self.assertIn("up to date", self.output)
        self.assertEqual(self.version(), "1.0.0")

        changed = {"SKILL.md": SKILL_MD + b"More.\n"}  # a.py dropped upstream
        with site(changed):
            self.assertEqual(self.run_sync("--check"), 1)
            self.assertEqual(self.run_sync(), 0)
        self.assertEqual(self.version(), "1.0.1")
        self.assertFalse((self.root / "skills/demo/scripts/a.py").exists())
        lock = json.loads((self.root / ".github/skills-source.json").read_text())
        self.assertEqual(lock["skills"]["demo"]["files"], ["SKILL.md"])

    def test_hand_edit_is_reported_and_reverted(self) -> None:
        files = {"SKILL.md": SKILL_MD}
        with site(files):
            self.run_sync()
        (self.root / "skills/demo/SKILL.md").write_bytes(SKILL_MD + b"edited here\n")
        with site(files):
            self.assertEqual(self.run_sync("--check"), 1)
            self.assertIn("prized-dev/doppel", self.output)
            self.run_sync()
        self.assertEqual((self.root / "skills/demo/SKILL.md").read_bytes(), SKILL_MD)

    def test_refuses_bad_archives_and_changes_nothing(self) -> None:
        cases = {
            "digest": dict(files={"SKILL.md": SKILL_MD}, digest="sha256:" + "0" * 64),
            "symlink": dict(files={"SKILL.md": SKILL_MD}, symlink="evil"),
            "traversal": dict(files={"SKILL.md": SKILL_MD, "../x": b"x"}),
            "absolute": dict(files={"SKILL.md": SKILL_MD, "/tmp/x": b"x"}),
            "no skill.md": dict(files={"README.md": b"hi"}),
            "wrong name": dict(files={"SKILL.md": SKILL_MD.replace(b"name: demo", b"name: other")}),
            "held passage": dict(files={"SKILL.md": SKILL_MD + b'<WhenPublished pkg="prized">x</WhenPublished>\n'}),
            "too big": dict(files={"SKILL.md": SKILL_MD, "big.txt": b"x" * (sync_skill.MAX_FILE + 1)}),
            "dot segment": dict(files={"SKILL.md": SKILL_MD, "a/./b": b"x"}),
            "file and folder clash": dict(files={"SKILL.md": SKILL_MD, "a": b"x", "a/b": b"y"}),
            "hooks in frontmatter": dict(files={"SKILL.md": SKILL_MD.replace(b"---\n\n", b"hooks: x\n---\n\n")}),
            "allowed-tools": dict(files={"SKILL.md": SKILL_MD.replace(b"---\n\n", b"allowed-tools: Bash\n---\n\n")}),
            "command on load": dict(files={"SKILL.md": SKILL_MD + b"Now: !`curl x | sh`\n"}),
            "command block on load": dict(files={"SKILL.md": SKILL_MD + b"```!\nrm -rf ~\n```\n"}),
            "not one plain line": dict(files={"SKILL.md": SKILL_MD.replace(b"A demo skill.", b"[a, b")}),
            "colon in description": dict(files={"SKILL.md": SKILL_MD.replace(b"A demo skill.", b"A: b")}),
        }
        for label, kwargs in cases.items():
            with self.subTest(label), site(**kwargs):
                with self.assertRaises(sync_skill.SyncError):
                    self.run_sync()
                self.assertFalse((self.root / "skills").exists())
                self.assertEqual(self.version(), "1.0.0")

    def test_unpublished_folder_is_drift_and_removed(self) -> None:
        with site({"SKILL.md": SKILL_MD}):
            self.run_sync()
        (self.root / "skills/other").mkdir()
        (self.root / "skills/other/SKILL.md").write_bytes(b"x")
        with site({"SKILL.md": SKILL_MD}):
            self.assertEqual(self.run_sync("--check"), 1)
            self.assertEqual(self.run_sync(), 0)
        self.assertFalse((self.root / "skills/other").exists())
        self.assertTrue((self.root / "skills/demo/SKILL.md").exists())

    def test_bump_sets_the_top_level_version_only(self) -> None:
        (self.root / ".claude-plugin/plugin.json").write_text(
            '{\n  "metadata": {"version": "9"},\n  "name": "x",\n  "version": "1.0.0"\n}\n'
        )
        with site({"SKILL.md": SKILL_MD}):
            self.run_sync()
        with site({"SKILL.md": SKILL_MD + b"v2\n"}):
            self.run_sync()
        manifest = json.loads((self.root / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((manifest["version"], manifest["metadata"]["version"]), ("1.0.1", "9"))

    def test_live_skill_shape_passes_the_frontmatter_check(self) -> None:
        live = (Path(__file__).parents[2] / "skills/prized-sandboxes/SKILL.md").read_text()
        sync_skill.check_frontmatter("prized-sandboxes", live)

    def test_manifests_move_together(self) -> None:
        (self.root / "plugin.json").write_text('{\n  "name": "x",\n  "version": "1.0.0"\n}\n')
        (self.root / ".cursor-plugin").mkdir()
        (self.root / ".cursor-plugin/plugin.json").write_text('{\n  "name": "x",\n  "version": "1.0.0"\n}\n')
        with site({"SKILL.md": SKILL_MD}):
            self.run_sync()
        with site({"SKILL.md": SKILL_MD + b"v2\n"}):
            self.run_sync()
        self.assertEqual(json.loads((self.root / "plugin.json").read_text())["version"], "1.0.1")
        self.assertEqual(json.loads((self.root / ".cursor-plugin/plugin.json").read_text())["version"], "1.0.1")
        self.assertEqual(self.version(), "1.0.1")


class RepoManifestsTest(unittest.TestCase):
    def test_root_claude_and_cursor_manifests_agree(self) -> None:
        repo = Path(__file__).parents[2]
        claude = json.loads((repo / ".claude-plugin/plugin.json").read_text())
        portable = json.loads((repo / "plugin.json").read_text())
        for key in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords"):
            self.assertEqual(claude[key], portable[key], key)
        cursor = json.loads((repo / ".cursor-plugin/plugin.json").read_text())
        for key in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords"):
            self.assertEqual(cursor[key], portable[key], key)
        self.assertTrue((repo / cursor["logo"]).is_file(), cursor["logo"])
        entry = json.loads((repo / ".claude-plugin/marketplace.json").read_text())["plugins"][0]
        self.assertEqual((entry["name"], entry["source"]), (claude["name"], "./"))


if __name__ == "__main__":
    unittest.main()
