# Prized skills

Skills that teach coding agents to use [Prized](https://prized.dev). The `prized-sandboxes` skill lets Claude Code, Codex, Cursor and other agents run code, shell commands and other agents in Prized Sandboxes, Linux microVMs the agent creates, runs commands in, forks and deletes, and tells them when a Prized box, a cloud Linux machine that stays on, fits better, for an agent that keeps working overnight or with your laptop closed. The agent loads it only when a task calls for it.

## Install

```bash
npx skills add prized-dev/skills -g -y -a claude-code -a codex -a cursor -a github-copilot
```

This installs the skill for every project in Claude Code, Codex, Cursor and GitHub Copilot, and in the agents that read `~/.agents/skills`, such as Gemini CLI, OpenCode, Cline and Zed. For an agent with its own skills folder, add `-a` with its name, such as `-a windsurf` or `-a goose`.

Make an API key with Sandboxes: Write on the [API keys page](https://prized.dev/dashboard/workspace/api-keys) and export it in the shell you start your agent from. New to Prized? [Sandboxes onboarding](https://prized.dev/onboarding/sandboxes) signs you up with free credit and no card.

```bash
export PRIZED_API_KEY=dcp_...
```

Then start a new session and ask your agent to run `python3 --version` in a Prized sandbox. It creates a sandbox, prints `Python 3.12.3` and deletes the sandbox.

The full guide is [Use Prized from your coding agent](https://prized.dev/docs/sandboxes-coding-agents).

### As a plugin

The same skill also ships as a plugin. One command finds Claude Code, Cursor, Codex, GitHub Copilot CLI and VS Code on your machine and installs the plugin in each.

```bash
npx plugins add prized-dev/skills
```

Run it again to update the copies it makes for Codex and VS Code.

Or by agent. In Claude Code, add this repo as a plugin marketplace and install the plugin.

```text
/plugin marketplace add prized-dev/skills
/plugin install prized@prized
```

In Codex, the same marketplace works from your shell.

```bash
codex plugin marketplace add prized-dev/skills
codex plugin add prized@prized
```

## What the skill runs

The skill is instructions in [SKILL.md](skills/prized-sandboxes/SKILL.md) plus three helper scripts the agent can copy into your project (Python standard library, and TypeScript with only `fetch`). The plugin has no hooks, MCP servers or background processes, and keeps no data of its own.

When the agent follows it:

- **Your key.** It reads `PRIZED_API_KEY` from your environment, or uses the `prized` CLI's existing sign-in, and sends the key only to `api.prized.dev` and each sandbox's edge address (`term.prized.dev` today).
- **Your work.** The code, commands and files you ask it to run go to your sandboxes. To run Claude Code or Codex in a sandbox, it passes the API key you give it for that agent to the sandbox as an encrypted environment variable. Only after you say yes, it copies a project or an agent's sign-in to a Prized box.
- **A sign-up, only if you ask.** With no Prized account, you can ask the agent to make one: it sends your email address, and your name and how you found Prized if you say, to `api.prized.dev`, which emails you a 6-digit code to give the agent.
- **Installs and docs.** It may install the `prized` CLI from `https://prized.dev/install.sh` (the CLI reports which commands ran, never their arguments or files, unless `PRIZED_NO_TELEMETRY=1`), or the SDK from PyPI (`prized`) or npm (`@prized/sdk`). It reads Prized's docs on `prized.dev`, such as `prized.dev/llms.txt` and `prized.dev/auth.md`, when it needs more detail.

Prized handles this data under its [privacy policy](https://prized.dev/privacy). Each sandbox it creates bills to your Prized workspace per second while it runs, and the skill tells the agent to set a maximum runtime and delete every sandbox. For work that should outlive a session, the skill points the agent at a Prized box, a cloud machine that bills by the hour while awake; it tells the agent to ask you before it makes one. Prices are on the [pricing page](https://prized.dev/pricing).

## Where the skill comes from

The skill is maintained with the Prized product and published at [prized.dev/SKILL.md](https://prized.dev/SKILL.md). A GitHub Action copies the published version into `skills/` every hour and checks it against the digest prized.dev lists, so `npx skills add prized-dev/skills` installs what prized.dev publishes, synced hourly. Edits to `skills/` here are overwritten. For a fix or a request, open an issue or email team@prized.dev.

## License

[Apache-2.0](LICENSE)
