# Prized for Claude Code

Give your coding agent its own computers in the cloud. With this plugin, Claude Code copies your project to a [Prized](https://prized.dev) box, a Linux machine that stays on, and keeps working there with your laptop closed. It also runs code, tests and agents in Prized Sandboxes, Linux microVMs that start in seconds and are deleted when the job is done. It asks you before anything that copies a file or a sign-in, or costs money.

The plugin has two skills, both driving the `prized` CLI. Claude loads each one only when a task calls for it.

- `prized-boxes`: put the project on a box, run Claude Code or a long job there, check on it, pause, resume, price and delete it.
- `prized-sandboxes`: run commands, tests and agents in sandboxes, one or many in parallel, and delete them when done; or build sandboxes into your app with Prized's SDK.

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

If you don't have the `prized` CLI yet, Claude gives you the one-line installer to run yourself. Then it has you run `prized login` (or makes your account from your email address and the 6-digit code Prized sends you), starts a box, copies the project to `~/code/<name>` on it once, with no sync, and runs the tests there. Then try "keep working on this on the box while I'm away", "is my box still running?", "pause my box" or "what does this box cost a month?".

New accounts get free credit, with no card. Boxes bill by the hour while awake and only for their disk while paused. Prices are on the [pricing page](https://prized.dev/pricing). Guides: [Claude Code on a box](https://prized.dev/claude-code), [Keep Claude Code running with your laptop closed](https://prized.dev/docs/keep-claude-code-running).

## Sandboxes

Sandboxes use the same `prized` sign-in. Ask Claude to run `python3 --version` in a Prized sandbox: it creates a sandbox, prints `Python 3.12.3` and deletes it. Then try "run the test suite in 4 sandboxes in parallel" or "try this script on a fresh Linux machine". Sandboxes bill per second while they run. Guide: [Use Prized from your coding agent](https://prized.dev/docs/sandboxes-coding-agents).

## What the plugin runs, and what it sends where

The plugin is instructions only ([boxes](skills/prized-boxes/SKILL.md), [sandboxes](skills/prized-sandboxes/SKILL.md)). It has no scripts, hooks, MCP servers or background processes of its own. Claude runs the commands below in your shell, with your usual permission prompts, and reads Prized's docs and pricing from prized.dev as it works.

**The CLI and its key.** Both skills run the `prized` CLI, which you install yourself from [prized.dev/install.sh](https://prized.dev/install.sh) when Claude gives you the line (Claude doesn't run the installer). The CLI keeps your Prized API key in `~/.config/prized` after `prized login` (or the email sign-up at [prized.dev/auth.md](https://prized.dev/auth.md)) and sends it only to Prized: its API at `api.prized.dev`, and for sandboxes each sandbox's edge address (`term.prized.dev` today). The skills never read the key, and tell Claude never to print, log or commit it.

**The boxes skill.** With your yes to each part, `prized setup` copies your project folder to your box (not `node_modules`, virtualenvs, build caches or `.env` files), and only if you say so, Claude Code's sign-in, MCP servers and settings (`--agent claude`), your GitHub CLI token and git identity (`--gh`) and parts of your local environment (`--env`). The skill passes `--no-advisor`, so setup does not send your project's manifests to Prized's environment advisor. It also starts the CLI's daemon, `prizedd`, for the box. The CLI reaches your box over an encrypted WireGuard tunnel (or the Prized relay over HTTPS when a network blocks it), uses Amazon S3 during setup, and updates itself from Prized's signed releases. It sends Prized usage counts (each command's name, version, OS, duration and exit code, and for some failures one word from a fixed list; never arguments, paths or file contents); `PRIZED_NO_TELEMETRY=1` turns that off ([CLI reference](https://prized.dev/docs/cli#usage-telemetry)). Boxes run in Prized's AWS account and bill your Prized workspace.

**The sandbox skill.** With your yes, Claude creates sandboxes, runs commands in them, and copies in the files a job needs and copies out its results. It passes none of your own keys or secrets into a sandbox unless you ask. Each sandbox bills to your Prized workspace per second while it runs; the skill has Claude set a maximum run time on each and delete every one when the job is done.

Prized's privacy policy: [prized.dev/privacy](https://prized.dev/privacy). How Prized handles your data and boxes: [Security](https://prized.dev/docs/security).

## Where the skills come from

Both skills are maintained here, written for Claude Code and the `prized` CLI: send changes as pull requests. For details that change, such as prices, limits and every API route, they send Claude to Prized's docs at the time, so the skills stay short. Prized also publishes a general skill for any agent at [prized.dev/SKILL.md](https://prized.dev/SKILL.md). For a fix or a request, open an [issue](https://github.com/prized-dev/skills/issues) or email team@prized.dev.

## License

[Apache-2.0](LICENSE)
