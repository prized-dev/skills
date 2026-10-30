#!/usr/bin/env python3
"""Mirror the skills prized.dev publishes into skills/<name>/ of this repo.

The source of truth is the skill in prized-dev/doppel
(controlplane/web/content/skills/). prized.dev builds it, resolves its
held passages, and publishes it for `npx skills add https://prized.dev`:

  /.well-known/agent-skills/index.json   agent-skills discovery 0.2.0
  /skills/<name>.tar.gz                  the skill folder, digest in the index

This script copies exactly that publication, so this repo can never say
more (or less) than prized.dev does. skills/ belongs to the mirror: a
folder prized.dev doesn't publish is removed. It only reads public URLs
and needs no token.

It fails closed, changing nothing, on anything a person should look at
first: a digest mismatch, an unsafe archive, or a skill that would run
something on its own (hooks, allowed-tools, `!` command lines), which this
plugin's README promises it doesn't.

  python3 .github/scripts/sync_skill.py           update skills/ and bump the version
  python3 .github/scripts/sync_skill.py --check   exit 1 if skills/ differs from prized.dev

Standard library only (Python 3.9+).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://prized.dev"
DISCOVERY = "/.well-known/agent-skills/index.json"
SCHEMA = "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
LOCK = Path(".github/skills-source.json")
# Every manifest that carries the plugin's version; they move together.
MANIFESTS = [
    Path(".claude-plugin/plugin.json"),
    Path("plugin.json"),
    Path(".cursor-plugin/plugin.json"),
    Path(".codex-plugin/plugin.json"),
]

NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")  # no "." or ".." segments
MAX_ARCHIVE = 5 * 1024 * 1024  # bytes, compressed
MAX_FILE = 256 * 1024  # bytes; Anthropic's directory holds bigger non-image files for review
MAX_TOTAL = 10 * 1024 * 1024  # bytes, all files of one skill
MAX_FILES = 100
HELD_TAGS = ("<UntilPublished", "<WhenPublished", "</UntilPublished>", "</WhenPublished>")
# Frontmatter keys a mirrored skill may use: the Agent Skills basics. Anything
# else (hooks, allowed-tools, context, ...) changes what the skill does on its
# own, so a person reviews it before it ships here.
FRONT_KEYS = {"name", "description", "compatibility", "metadata", "license"}
# `!`cmd`` in skill text runs a command when the skill loads; so does a ```! block.
RUNS_ON_LOAD = re.compile(r"!`|^\s*```!", re.M)


class SyncError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise SyncError(f"{req.full_url}: redirected to {newurl}; refusing")


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(url: str, limit: int) -> bytes:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise SyncError(f"{url}: not https")
    req = urllib.request.Request(url, headers={"User-Agent": "prized-dev-skills-sync/1"})
    try:
        with _OPENER.open(req, timeout=30) as resp:
            data = resp.read(limit + 1)
    except urllib.error.HTTPError as err:
        raise SyncError(f"{url}: HTTP {err.code}") from None
    if len(data) > limit:
        raise SyncError(f"{url}: larger than {limit} bytes")
    return data


def check_frontmatter(name: str, text: str) -> None:
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not front:
        raise SyncError(f"{name}: SKILL.md has no frontmatter")
    keys = {}
    for line in front.group(1).split("\n"):
        if line.startswith((" ", "\t")):  # a metadata child: "  key: value"
            if not re.match(r"^  [A-Za-z0-9_-]+: \S.*$", line):
                raise SyncError(f"{name}: unexpected frontmatter line {line!r}")
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?: (.*))?$", line)
        if not match:
            raise SyncError(f"{name}: unexpected frontmatter line {line!r}")
        keys[match.group(1)] = (match.group(2) or "").strip()
    extra = set(keys) - FRONT_KEYS
    if extra:
        raise SyncError(f"{name}: frontmatter key(s) {sorted(extra)} need a person to review this skill first")
    if keys.get("name") != name:
        raise SyncError(f"{name}: SKILL.md frontmatter does not say name: {name}")
    for key in ("description", "compatibility"):
        value = keys.get(key)
        if key == "description" and not value:
            raise SyncError(f"{name}: SKILL.md frontmatter has no description")
        # One plain line: no flow collections, block scalars, anchors or quotes to balance.
        if value and (value[0] in "[{|>&*!%@`'\"" or ": " in value or " #" in value):
            raise SyncError(f"{name}: frontmatter {key} must be one plain YAML line")
    if "metadata" in keys and keys["metadata"]:
        raise SyncError(f"{name}: frontmatter metadata must be a nested map")


def skill_files(name: str, archive: bytes) -> dict[str, bytes]:
    """The archive's files, checked, read as a stream with running caps."""
    files: dict[str, bytes] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r|gz") as tar:
        for member in tar:
            if member.isdir():
                continue
            if not member.isfile():
                raise SyncError(f"{name}: {member.name!r} is not a regular file")
            path = member.name[2:] if member.name.startswith("./") else member.name
            if not path or not all(SEGMENT_RE.match(seg) for seg in path.split("/")):
                raise SyncError(f"{name}: unsafe path {member.name!r}")
            if path in files or any(p.startswith(path + "/") or path.startswith(p + "/") for p in files):
                raise SyncError(f"{name}: {path} clashes with another entry")
            if member.size > MAX_FILE:
                raise SyncError(f"{name}: {path} is {member.size} bytes (limit {MAX_FILE})")
            total += member.size
            if len(files) + 1 > MAX_FILES or total > MAX_TOTAL:
                raise SyncError(f"{name}: more than {MAX_FILES} files or {MAX_TOTAL} bytes")
            handle = tar.extractfile(member)
            if handle is None:
                raise SyncError(f"{name}: cannot read {path}")
            files[path] = handle.read(MAX_FILE + 1)
    skill_md = files.get("SKILL.md")
    if skill_md is None:
        raise SyncError(f"{name}: no SKILL.md at the archive root")
    check_frontmatter(name, skill_md.decode("utf-8"))
    for path, data in files.items():
        if not path.endswith(".md"):
            continue
        text = data.decode("utf-8")
        if any(tag in text for tag in HELD_TAGS):
            raise SyncError(f"{name}: {path} still has a held passage; prized.dev should resolve it")
        if RUNS_ON_LOAD.search(text):
            raise SyncError(f"{name}: {path} has a command that runs when the skill loads; review it first")
    return files


def published(site: str) -> dict[str, dict]:
    """{name: {"digest", "files"}} for every archive skill prized.dev lists."""
    index_url = site + DISCOVERY
    index = json.loads(fetch(index_url, 1024 * 1024))
    if index.get("$schema") != SCHEMA:
        raise SyncError(f"{index_url}: unexpected $schema {index.get('$schema')!r}")
    skills: dict[str, dict] = {}
    for entry in index.get("skills", []):
        name, url, digest = entry.get("name"), entry.get("url"), entry.get("digest", "")
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise SyncError(f"{index_url}: bad skill name {name!r}")
        if entry.get("type") != "archive":
            raise SyncError(f"{index_url}: {name} is {entry.get('type')!r}; this script mirrors archives only")
        archive_url = urllib.parse.urljoin(index_url, str(url))
        if urllib.parse.urlsplit(archive_url)[:2] != urllib.parse.urlsplit(site)[:2]:
            raise SyncError(f"{name}: archive {archive_url} is not on {site}")
        archive = fetch(archive_url, MAX_ARCHIVE)
        actual = "sha256:" + hashlib.sha256(archive).hexdigest()
        if actual != digest:
            raise SyncError(f"{name}: archive digest {actual} does not match the index's {digest}")
        skills[name] = {"digest": digest, "files": skill_files(name, archive)}
    if not skills:
        raise SyncError(f"{index_url}: lists no skills")
    return skills


def local_files(folder: Path) -> dict[str, bytes]:
    if not folder.is_dir():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def bump(version: str) -> str:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        raise SyncError(f"version {version!r} is not MAJOR.MINOR.PATCH")
    major, minor, patch = (int(x) for x in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def plan_bump(root: Path) -> tuple[str, dict[Path, str]]:
    """The next patch version and each manifest's new text; nothing is written."""
    present = [root / m for m in MANIFESTS if (root / m).is_file()]
    versions = {json.loads(p.read_text())["version"] for p in present}
    if len(versions) != 1:
        raise SyncError(f"manifests disagree on version: {sorted(versions)}")
    new = bump(versions.pop())
    edits = {}
    for path in present:
        # Rewrite only the top-level version line, keeping the file's formatting.
        text = re.sub(r'^(  "version":\s*")[^"]*(")', rf"\g<1>{new}\g<2>", path.read_text(), count=1, flags=re.M)
        if json.loads(text).get("version") != new:
            raise SyncError(f"{path}: could not set the top-level version")
        edits[path] = text
    return new, edits


def write_skills(root: Path, skills: dict[str, dict], remove: list[str]) -> None:
    """Stage every changed skill in a temp folder first, then swap folders in."""
    base = root / "skills"
    base.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".sync-", dir=base))
    try:
        for name, skill in skills.items():
            for rel, data in skill["files"].items():
                dest = stage / name / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        for name in skills:
            final, old = base / name, base / f".old-{name}"
            if final.exists():
                final.rename(old)
            (stage / name).rename(final)
            shutil.rmtree(old, ignore_errors=True)
        for name in remove:
            shutil.rmtree(base / name)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", default=os.environ.get("PRIZED_SITE", SITE))
    parser.add_argument("--root", default=".", help="the repo root (default: .)")
    parser.add_argument("--check", action="store_true", help="report drift, change nothing")
    args = parser.parse_args()
    site = args.site.rstrip("/")
    if urllib.parse.urlsplit(site).scheme != "https":
        raise SyncError(f"--site must be https: {site}")
    root = Path(args.root)

    skills = published(site)
    base = root / "skills"
    present = sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")) if base.is_dir() else []
    changed_skills = {n: s for n, s in sorted(skills.items()) if local_files(base / n) != s["files"]}
    extra = [n for n in present if n not in skills]
    changed = [f"{n} ({s['digest'][:19]})" for n, s in changed_skills.items()]
    changed += [f"{n!r} (not published, removed)" for n in extra]

    if args.check:
        if changed:
            print("skills/ differs from " + site + ": " + ", ".join(changed))
            print("The skill is edited in prized-dev/doppel and mirrored here; run the Sync skill workflow.")
            return 1
        print(f"skills/ matches {site}: " + ", ".join(sorted(skills)))
        return 0
    if not changed:
        print(f"up to date with {site}: " + ", ".join(sorted(skills)))
        return 0

    lock_path = root / LOCK
    first_sync = not lock_path.is_file()
    # Plan the version first, so a manifest problem changes nothing.
    version, edits = ("unchanged (first sync)", {}) if first_sync else plan_bump(root)
    write_skills(root, changed_skills, extra)
    for path, text in edits.items():
        path.write_text(text)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({
        "site": site,
        "note": "Written by .github/scripts/sync_skill.py. Edit the skill in prized-dev/doppel, not here.",
        "skills": {n: {"digest": s["digest"], "files": sorted(s["files"])} for n, s in sorted(skills.items())},
    }, indent=2) + "\n")
    summary = "; ".join(changed).replace("\n", " ")
    print(f"synced {summary}; plugin version {version}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as handle:
            handle.write(f"changed={summary}\nversion={version}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SyncError, OSError, ValueError, tarfile.TarError) as err:
        print(f"sync failed: {err}", file=sys.stderr)
        sys.exit(2)
