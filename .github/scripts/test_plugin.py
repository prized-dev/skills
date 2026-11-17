"""Checks on plugins/prized that Claude's plugin directory would otherwise hold or block.

  python3 -m unittest discover -s .github/scripts

Standard library only (Python 3.9+).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins/prized"
SKILLS = PLUGIN / "skills"
# What the directory accepts from an organization it hasn't verified: no scripts or programs.
ACCEPTED = (".md", ".txt", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".gif", ".webp")
# Frontmatter a skill may use: the Agent Skills basics. Anything else (hooks, allowed-tools,
# context, ...) changes what a skill does on its own.
FRONT_KEYS = {"name", "description", "compatibility", "metadata", "license"}
# `!`cmd`` in skill text runs a command when the skill loads; so does a ```! block.
RUNS_ON_LOAD = re.compile(r"!`|^\s*```!", re.M)
# A download piped into a shell: the directory holds a skill that runs one.
PIPE_TO_SHELL = re.compile(r"\b(curl|wget|irm|iwr|Invoke-RestMethod|Invoke-WebRequest)\b[^\n`]*\|\s*(sh|bash|zsh|iex|Invoke-Expression)\b", re.I)
# Reading a key from the user's environment and sending it on: the directory holds that too,
# even in a README example. The CLI keeps the key; the skills never read it.
ENV_KEY = re.compile(r"PRIZED_API_KEY|\$\{?[A-Z0-9_]*(API_KEY|TOKEN|SECRET)\b")


def text_files() -> list[Path]:
    return sorted(p for p in PLUGIN.rglob("*") if p.is_file() and p.suffix in (".md", ".json"))


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text()
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not front:
        raise AssertionError(f"{path}: no frontmatter")
    keys = {}
    for line in front.group(1).split("\n"):
        if line.startswith((" ", "\t")):
            if not re.match(r"^  [A-Za-z0-9_-]+: \S.*$", line):
                raise AssertionError(f"{path}: unexpected frontmatter line {line!r}")
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?: (.*))?$", line)
        if not match:
            raise AssertionError(f"{path}: unexpected frontmatter line {line!r}")
        keys[match.group(1)] = (match.group(2) or "").strip()
    return keys


class PluginTest(unittest.TestCase):
    def test_only_files_the_directory_accepts(self) -> None:
        for path in sorted(p for p in PLUGIN.rglob("*") if p.is_file()):
            rel = path.relative_to(PLUGIN).as_posix()
            with self.subTest(rel):
                self.assertTrue(rel == "LICENSE" or rel.lower().endswith(ACCEPTED), rel)
                self.assertFalse(path.read_bytes().startswith(b"#!"), rel)

    def test_no_download_piped_into_a_shell(self) -> None:
        for path in sorted(SKILLS.rglob("*.md")):
            with self.subTest(path.relative_to(PLUGIN).as_posix()):
                self.assertIsNone(PIPE_TO_SHELL.search(path.read_text()))

    def test_no_key_read_from_the_environment(self) -> None:
        for path in text_files():
            with self.subTest(path.relative_to(PLUGIN).as_posix()):
                self.assertIsNone(ENV_KEY.search(path.read_text()))

    def test_skills_have_plain_frontmatter_and_run_nothing_on_load(self) -> None:
        skills = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertEqual([p.parent.name for p in skills], ["prized-boxes", "prized-sandboxes"])
        for path in skills:
            with self.subTest(path.parent.name):
                keys = frontmatter(path)
                self.assertLessEqual(set(keys), FRONT_KEYS)
                self.assertEqual(keys.get("name"), path.parent.name)
                for key in ("description", "compatibility"):
                    value = keys.get(key, "")
                    self.assertTrue(value or key != "description", key)
                    # One plain line: no flow collections, block scalars, anchors or quotes.
                    self.assertFalse(value and (value[0] in "[{|>&*!%@`'\"" or ": " in value or " #" in value), key)
                self.assertIsNone(RUNS_ON_LOAD.search(path.read_text()))

    def test_manifests_agree(self) -> None:
        claude = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        portable = json.loads((PLUGIN / "plugin.json").read_text())
        for key in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords"):
            self.assertEqual(claude[key], portable[key], key)
        cursor = json.loads((PLUGIN / ".cursor-plugin/plugin.json").read_text())
        for key in ("name", "displayName", "version", "description", "homepage", "repository", "license", "keywords"):
            self.assertEqual(cursor[key], claude[key], key)
        # Cursor's schema (cursor/plugins schemas/plugin.schema.json) rejects any other key,
        # and allows only name and email in author.
        allowed = {"name", "displayName", "version", "description", "author", "homepage", "repository",
                   "license", "keywords", "logo", "category", "tags", "publisher", "minClientVersions",
                   "commands", "agents", "skills", "rules", "hooks", "mcpServers", "variables"}
        self.assertLessEqual(set(cursor), allowed)
        self.assertEqual(cursor["author"], {k: portable["author"][k] for k in ("name", "email")})
        self.assertTrue((PLUGIN / cursor["logo"]).is_file(), cursor["logo"])
        self.assertTrue((PLUGIN / claude["icon"]).is_file(), claude["icon"])
        market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
        entry = market["plugins"][0]
        self.assertEqual((entry["name"], entry["source"]), (claude["name"], "./plugins/prized"))
        self.assertEqual(entry["description"], claude["description"])


if __name__ == "__main__":
    unittest.main()
