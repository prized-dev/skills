#!/usr/bin/env python3
"""Check the ChatGPT plugin in chatgpt/ against OpenAI's published package rules.

OpenAI has no public offline validator: the submission portal validates the
ZIP on upload. This script applies the rules OpenAI documents, so a mistake
shows up here first:

  https://developers.openai.com/plugins/deploy/submission-errors
  https://developers.openai.com/plugins/deploy/submission#manifest-fields
  https://developers.openai.com/plugins/deploy/desktop-only
  https://agent-plugins.org/schemas/1.0.0/plugin.schema.json

It also enforces rules of our own: the skill stays provider-neutral (no
"Claude"), nothing in the package quotes a price, and the package keeps out
what the Claude plugin keeps out (.github/scripts/test_plugin.py): scripts and
other non-text files, a download piped into a shell, and an API key read from
the environment.

  python3 .github/scripts/check_chatgpt_plugin.py chatgpt
  python3 .github/scripts/check_chatgpt_plugin.py chatgpt --zip prized-chatgpt.zip

Standard library only. Exit 0 when the package passes, 1 with a list of
problems otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ROOT_KEYS = {"$schema", "name", "version", "description", "author", "homepage",
             "repository", "license", "keywords", "extensions"}
AUTHOR_KEYS = {"name", "email", "url"}
CATEGORIES = {"Productivity", "Creativity", "Developer Tools", "Business & Operations",
              "Data & Analytics", "Communication", "Education & Research", "Security",
              "Finance", "Healthcare", "Travel", "Entertainment", "Other"}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
NAME_SCHEMA = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
NAME_SUBMIT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # OpenAI: lowercase letters, numbers and single hyphens
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Control characters other than tab/newline, Unicode line and paragraph separators, and
# invisible formatting characters (OpenAI: "supported text").
UNSUPPORTED = re.compile("[\x00-\x08\x0b-\x1f\x7f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
PRICE = re.compile(r"\$\s?\d")
PROMO = re.compile(r"free (credit|trial|tier)|\btrial\b|no card|discount|promo|coupon", re.I)
FORBIDDEN_FILES = (".app.json", ".mcp.json", "mcp.json", "hooks", ".claude-plugin", ".codex-plugin")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg")
# Text and images only: no scripts or programs in the package.
ACCEPTED = (".md", ".txt", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".gif", ".webp")
# A download piped into a shell: the user runs the CLI's installer themselves.
PIPE_TO_SHELL = re.compile(r"\b(curl|wget|irm|iwr|Invoke-RestMethod|Invoke-WebRequest)\b[^\n`]*\|\s*(sh|bash|zsh|iex|Invoke-Expression)\b", re.I)
# Reading a key from the user's environment: the CLI keeps the key; the skill never reads it.
ENV_KEY = re.compile(r"PRIZED_API_KEY|\$\{?[A-Z0-9_]*(API_KEY|TOKEN|SECRET)\b")


def text_ok(value: str, one_line: bool) -> bool:
    if UNSUPPORTED.search(value):
        return False
    if one_line and ("\n" in value or "\r" in value):
        return False
    return bool(value.strip())


def https_ok(url: object, limit: int = 1024) -> bool:
    return (isinstance(url, str) and url.startswith("https://") and len(url) <= limit
            and "@" not in url.split("/")[2] and " " not in url and len(url) > len("https://"))


def luminance(hex_color: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def check_image(root: Path, field: str, rel: object, problems: list[str]) -> None:
    if not isinstance(rel, str) or not rel.startswith("./"):
        problems.append(f"{field}: must be a ./-prefixed path inside the plugin")
        return
    path = (root / rel).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        problems.append(f"{field}: {rel} is not a file inside the plugin")
        return
    if not rel.lower().endswith(IMAGE_EXT):
        problems.append(f"{field}: {rel} must be PNG, JPEG, WebP or SVG")
        return
    data = path.read_bytes()
    if len(data) > 5 * 1024 * 1024:
        problems.append(f"{field}: {rel} is over 5 MiB")
    if not rel.lower().endswith(".png"):
        problems.append(f"{field}: {rel}: this check verifies PNG icons only; use a square PNG")
        return
    size = png_size(data)
    if size is None:
        problems.append(f"{field}: {rel} is not a PNG")
        return
    w, h = size
    if w != h:
        problems.append(f"{field}: {rel} is {w}x{h}, must be square")
    if w < 48 or w > 4096:
        problems.append(f"{field}: {rel} is {w}px, must be 48 to 4096")


def front_matter(text: str) -> tuple[dict[str, str], str] | None:
    """The simple `key: value` front matter our skills use. Nested keys are skipped."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            return None
        value = value.strip()
        if value[:1] in (">", "|", "[", "{", "&", "*", "!"):
            return None  # valid YAML maybe, but not the plain one-line form this check can read
        fields[key.strip()] = value.strip('"').strip("'")
    return fields, text[end + 4:].lstrip("-\n")


def check_skills(root: Path, plugin_name: str, problems: list[str]) -> list[str]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        problems.append("skills/: missing; a skills-only plugin needs at least one skill")
        return []
    names: list[str] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            problems.append(f"skills/{entry.name}: skill directories must not start with '.'")
            continue
        if entry.is_symlink() or not entry.is_dir():
            problems.append(f"skills/{entry.name}: not imported; each skill must be a real directory")
            continue
        manifest = entry / "SKILL.md"
        if not manifest.is_file():
            problems.append(f"skills/{entry.name}: missing SKILL.md")
            continue
        try:
            text = manifest.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"skills/{entry.name}/SKILL.md: not UTF-8")
            continue
        parsed = front_matter(text)
        if parsed is None:
            problems.append(f"skills/{entry.name}/SKILL.md: needs YAML front matter between --- lines")
            continue
        fields, body = parsed
        name, desc = fields.get("name", ""), fields.get("description", "")
        if not name:
            problems.append(f"skills/{entry.name}/SKILL.md: name is required")
        if not desc:
            problems.append(f"skills/{entry.name}/SKILL.md: description is required")
        elif len(desc) > 1024:
            problems.append(f"skills/{entry.name}/SKILL.md: description is {len(desc)} characters, max 1024")
        if not body.strip():
            problems.append(f"skills/{entry.name}/SKILL.md: instructions must not be empty")
        if len(f"{plugin_name}:{name}") > 64:
            problems.append(f"skills/{entry.name}: '{plugin_name}:{name}' is over 64 characters")
        if name in names:
            problems.append(f"skills/{entry.name}: duplicate skill name {name}")
        if "metadata" in fields:
            problems.append(f"skills/{entry.name}/SKILL.md: OpenAI ignores `metadata`; drop it")
        if re.search(r"\bClaude\b", text):
            problems.append(f"skills/{entry.name}/SKILL.md: mentions Claude; OpenAI asks for provider-neutral skills")
        if PRICE.search(text) or PROMO.search(text):
            problems.append(f"skills/{entry.name}/SKILL.md: quotes a price or an offer; link https://prized.dev/pricing instead")
        if PIPE_TO_SHELL.search(text):
            problems.append(f"skills/{entry.name}/SKILL.md: pipes a download into a shell; give the user the install line to run instead")
        names.append(name)
    for stray in skills_dir.iterdir():
        if stray.is_file():
            problems.append(f"skills/{stray.name}: files directly under skills/ are not imported")
    if not names:
        problems.append("skills/: no valid skill")
    return names


def check(root: Path) -> list[str]:
    problems: list[str] = []
    manifest_path = root / "plugin.json"
    if not manifest_path.is_file():
        return [f"{manifest_path}: missing"]
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"plugin.json: not valid JSON ({e})"]
    if not isinstance(m, dict):
        return ["plugin.json: must be a JSON object"]

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if not rel.lower().endswith(ACCEPTED) or path.read_bytes().startswith(b"#!"):
            problems.append(f"{rel}: only text and images in the package, no scripts")
        elif rel.endswith((".md", ".json")) and ENV_KEY.search(path.read_text(encoding="utf-8", errors="replace")):
            problems.append(f"{rel}: reads a key from the environment; the CLI keeps the key")

    for name in FORBIDDEN_FILES:
        if (root / name).exists():
            problems.append(f"{name}: not allowed in a skills-only directory submission")

    # Agent Plugins 1.0.0 schema.
    if m.get("$schema") != SCHEMA:
        problems.append(f"$schema: must be {SCHEMA}")
    for key in sorted(set(m) - ROOT_KEYS):
        problems.append(f"{key}: not allowed at the root by the Agent Plugins schema")
    name = m.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= 64) or not NAME_SCHEMA.match(name) or not NAME_SUBMIT.match(name):
        problems.append("name: lowercase letters, digits and single hyphens, at most 64 characters")
        name = str(name)
    if not isinstance(m.get("version"), str) or not SEMVER.match(m["version"]) or len(m["version"]) > 64:
        problems.append("version: must be a semantic version such as 1.0.0")
    desc = m.get("description")
    if not isinstance(desc, str) or not text_ok(desc, False) or len(desc) > 1024:
        problems.append("description: required, supported text, at most 1,024 characters")
    author = m.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        problems.append("author.name: required")
    else:
        for key in sorted(set(author) - AUTHOR_KEYS):
            problems.append(f"author.{key}: not allowed by the Agent Plugins schema")
        if len(author["name"]) > 120:
            problems.append("author.name: at most 120 characters")
        if "url" in author and not https_ok(author["url"], 2048):
            problems.append("author.url: must be an HTTPS URL")
    if "homepage" in m and not https_ok(m["homepage"], 2048):
        problems.append("homepage: must be an HTTPS URL")
    if "keywords" in m and (not isinstance(m["keywords"], list) or not all(isinstance(k, str) for k in m["keywords"])):
        problems.append("keywords: must be a list of strings")

    extensions = m.get("extensions") or {}
    if not isinstance(extensions, dict):
        problems.append("extensions: must be an object")
        extensions = {}
    ext = extensions.get("com.openai")
    if not isinstance(ext, dict):
        problems.append("extensions.com.openai: required for the ChatGPT listing")
        ext = {}
    for key in ("apps", "hooks", "mcpServers", "skills"):
        if key in ext:
            problems.append(f"extensions.com.openai.{key}: not allowed in a skills-only directory submission")
    if ext.get("requires_local_executor") is not True:
        problems.append("extensions.com.openai.requires_local_executor: must be true; the skill runs the prized CLI on the user's computer")
    review = ext.get("review") or {}
    if not isinstance(review, dict):
        problems.append("extensions.com.openai.review: must be an object")
        review = {}
    if review.get("test_cases"):
        problems.append("extensions.com.openai.review.test_cases: only for a plugin with exactly one MCP server")
    for key in ("test_credentials", "reviewer_instructions"):
        if key in review:
            problems.append(f"review.{key}: never in the package; enter it in the portal")

    ui = ext.get("interface")
    if not isinstance(ui, dict):
        problems.append("extensions.com.openai.interface: required")
        ui = {}
    for field, limit, one_line in (("displayName", 30, True), ("shortDescription", 30, True),
                                   ("longDescription", 4000, False), ("developerName", 80, True)):
        value = ui.get(field)
        if not isinstance(value, str) or not text_ok(value, one_line):
            problems.append(f"interface.{field}: required" + (", one line" if one_line else ""))
        elif len(value) > limit:
            problems.append(f"interface.{field}: {len(value)} characters, at most {limit} for the directory")
    if ui.get("category") not in CATEGORIES:
        problems.append(f"interface.category: one of {', '.join(sorted(CATEGORIES))}")
    caps = ui.get("capabilities", [])
    if not isinstance(caps, list) or len(caps) > 20 or not all(
            isinstance(c, str) and text_ok(c, True) and len(c) <= 120 for c in caps):
        problems.append("interface.capabilities: at most 20 one-line labels of at most 120 characters")
    for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
        if field in ui and not https_ok(ui[field]):
            problems.append(f"interface.{field}: must be an HTTPS URL of at most 1,024 characters")
    prompts = ui.get("defaultPrompt", [])
    prompts = [prompts] if isinstance(prompts, str) else prompts
    if not isinstance(prompts, list) or len(prompts) > 3:
        problems.append("interface.defaultPrompt: at most three prompts")
    else:
        seen = set()
        for p in prompts:
            if not isinstance(p, str) or not text_ok(p, True) or len(p) > 128:
                problems.append(f"interface.defaultPrompt: {p!r} must be one line of at most 128 characters")
            elif "@" in p:
                problems.append(f"interface.defaultPrompt: {p!r} must not @mention")
            key = " ".join(str(p).split()).casefold()
            if key in seen:
                problems.append(f"interface.defaultPrompt: {p!r} is a duplicate")
            seen.add(key)
    if "brandColor" in ui:
        if not isinstance(ui["brandColor"], str) or not HEX.match(ui["brandColor"]):
            problems.append("interface.brandColor: a six-digit hex color")
        elif contrast(ui["brandColor"], "#FFFFFF") < 2:
            problems.append("interface.brandColor: needs 2:1 contrast against white")
    if "brandColorDark" in ui:
        if not isinstance(ui["brandColorDark"], str) or not HEX.match(ui["brandColorDark"]):
            problems.append("interface.brandColorDark: a six-digit hex color")
        elif contrast(ui["brandColorDark"], "#212121") < 2:
            problems.append("interface.brandColorDark: needs 2:1 contrast against #212121")
    for field in ("logo", "composerIcon"):
        if field not in ui:
            problems.append(f"interface.{field}: required")
        else:
            check_image(root, f"interface.{field}", ui[field], problems)
    pub = ext.get("publication") or {}
    if not isinstance(pub, dict):
        problems.append("extensions.com.openai.publication: must be an object")
        pub = {}
    listing = " ".join([str(m.get("description", "")), str(pub.get("release_notes", ""))]
                       + [str(ui.get(f, "")) for f in ("displayName", "shortDescription", "longDescription")]
                       + [str(x) for x in (caps if isinstance(caps, list) else [])]
                       + [str(x) for x in (prompts if isinstance(prompts, list) else [])])
    if PRICE.search(listing) or PROMO.search(listing):
        problems.append("interface: OpenAI does not allow prices, free trials or promotions in the listing")
    if re.search(r"\b(MCP|Plugin)\b", str(ui.get("displayName", ""))):
        problems.append("interface.displayName: do not append MCP or Plugin to the name")

    if "release_notes" in pub and (not isinstance(pub["release_notes"], str) or not pub["release_notes"].strip()):
        problems.append("publication.release_notes: must be non-empty text")

    check_skills(root, name, problems)
    return problems


def build_zip(root: Path, out: Path) -> int:
    files = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                   and "__pycache__" not in p.parts and p.suffix != ".zip"
                   and p.name != ".DS_Store" and p.relative_to(root).as_posix() != "README.md")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, path.relative_to(root).as_posix())
    return len(files)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", type=Path, help="the plugin folder, e.g. chatgpt")
    ap.add_argument("--zip", type=Path, help="also write the upload ZIP here (plugin files at its root, no README)")
    args = ap.parse_args(argv)
    problems = check(args.root)
    if problems:
        print(f"{args.root}: {len(problems)} problem(s)")
        for p in problems:
            print("  - " + p)
        return 1
    print(f"{args.root}: passes OpenAI's documented package rules")
    if args.zip:
        n = build_zip(args.root, args.zip)
        print(f"wrote {args.zip} ({n} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
