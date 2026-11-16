# Prized for Claude Code

Give your coding agent a cloud dev box. With this plugin, Claude Code copies your project to a [Prized](https://prized.dev) box, a Linux machine that stays on, and keeps working there with your laptop closed. It can also create, check on, pause and resume the box, and tell you what it costs. It asks you before anything that installs software, copies a file or a sign-in, or costs money.

The plugin has two skills. Claude loads each one only when a task calls for it.

- `prized-boxes`: boxes, through the `prized` CLI.
- `prized-sandboxes`: Prized Sandboxes, Linux microVMs your code creates, runs commands in and deletes, for throwaway jobs.

## Install

In Claude Code, add this repo as a plugin marketplace and install the plugin.

```text
/plugin marketplace add prized-dev/skills
/plugin install prized@prized
```

Or, for Claude Code, Cursor, Codex, GitHub Copilot CLI and VS Code at once:

```bash
npx plugins add prized-dev/skills
```

## Try it

Start a new Claude Code session in a project and ask:

```text
Put this project on a Prized box and run its tests there.
```

Claude installs the `prized` CLI if you don't have it, has you run `prized login` (or makes your account from your email address and the 6-digit code Prized sends you), starts a box, copies the project to `~/code/<name>` on it once, with no sync, and runs the tests there. Then try "keep working on this on the box while I'm away", "is my box still running?", "pause my box" or "what does this box cost a month?".

New accounts get free credit, with no card. Boxes bill by the hour while awake and only for their disk while paused. Prices are on the [pricing page](https://prized.dev/pricing). Guides: [Claude Code on a box](https://prized.dev/claude-code), [Keep Claude Code running with your laptop closed](https://prized.dev/docs/keep-claude-code-running).

## Sandboxes

The sandbox skill's code reads an API key from `PRIZED_API_KEY`. Make one with Sandboxes: Write on the [API keys page](https://prized.dev/dashboard/workspace/api-keys) and export it in the shell you start Claude Code from. Then ask Claude to run `python3 --version` in a Prized sandbox: it creates a sandbox, prints `Python 3.12.3` and deletes it. Guide: [Use Prized from your coding agent](https://prized.dev/docs/sandboxes-coding-agents).

## What the plugin runs, and what it sends where

The plugin is instructions ([boxes](skills/prized-boxes/SKILL.md), [sandboxes](skills/prized-sandboxes/SKILL.md)) plus three helper scripts the sandbox skill can copy into your project (Python standard library, and TypeScript with only `fetch`). It has no hooks, MCP servers or background processes of its own. Claude runs the commands below in your shell, with your usual permission prompts, and reads Prized's docs and pricing from prized.dev as it works.

**The key.** Both skills use your own Prized API key. The `prized` CLI keeps it in `~/.config/prized` after `prized login` (or the email sign-up at [prized.dev/auth.md](https://prized.dev/auth.md)) and uses `PRIZED_API_KEY` instead when that is set. The sandbox skill's code reads `PRIZED_API_KEY`. The key goes only to Prized: its API at `api.prized.dev`, and for sandboxes each sandbox's edge address (`term.prized.dev` today). The skills tell Claude never to print, log or commit it.

**The boxes skill** runs the `prized` CLI, which it may install from `https://prized.dev/install.sh`. With your yes to each part, `prized setup` copies your project folder to your box (not `node_modules`, virtualenvs, build caches or `.env` files), and only if you say so, Claude Code's sign-in, MCP servers and settings (`--agent claude`), your GitHub CLI token and git identity (`--gh`) and parts of your local environment (`--env`). The skill passes `--no-advisor`, so setup does not send your project's manifests to Prized's environment advisor. It also starts the CLI's daemon, `prizedd`, for the box. The CLI reaches your box over an encrypted WireGuard tunnel (or the Prized relay over HTTPS when a network blocks it), uses Amazon S3 during setup, and updates itself from Prized's signed releases. It sends Prized usage counts (each command's name, version, OS, duration and exit code, and for some failures one word from a fixed list; never arguments, paths or file contents); `PRIZED_NO_TELEMETRY=1` turns that off ([CLI reference](https://prized.dev/docs/cli#usage-telemetry)). Boxes run in Prized's AWS account and bill your Prized workspace.

**The sandbox skill** may install the same CLI. Each sandbox it creates bills to your Prized workspace per second while it runs, and the skill tells Claude to set a maximum runtime and delete every sandbox.

Prized's privacy policy: [prized.dev/privacy](https://prized.dev/privacy). How Prized handles your data and boxes: [Security](https://prized.dev/docs/security).

## Where the skills come from

`skills/prized-boxes` is maintained here: send changes as pull requests. `skills/prized-sandboxes` is maintained with the Prized product and published at [prized.dev/SKILL.md](https://prized.dev/SKILL.md); a GitHub Action copies the published version into `skills/` every hour and checks it against the digest prized.dev lists, so edits to it here are overwritten. For a fix or a request, open an [issue](https://github.com/prized-dev/skills/issues) or email team@prized.dev.

## License

[Apache-2.0](LICENSE)
