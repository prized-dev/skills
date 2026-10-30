# Prized skills

Skills that teach coding agents to use [Prized](https://prized.dev). The `prized-sandboxes` skill lets Claude Code, Codex, Cursor and other agents run code, shell commands and other agents in Prized Sandboxes, Linux microVMs the agent creates, runs commands in, forks and deletes. The agent loads it only when a task calls for it.

## Install

Make an API key with Sandboxes: Write on the [API keys page](https://prized.dev/dashboard/workspace/api-keys) and export it in the shell you start your agent from. New to Prized? [Sandboxes onboarding](https://prized.dev/onboarding/sandboxes) signs you up with free credit and no card.

```bash
export PRIZED_API_KEY=dcp_...
```

One command for any of them. It finds Claude Code, Cursor, Codex, GitHub Copilot CLI and VS Code on your machine and installs the plugin in each.

```bash
npx plugins add prized-dev/skills
```

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

For any other agent (OpenCode, Goose, Windsurf, Cline, Zed and more), install the skill with the `skills` CLI. It asks which agents get it.

```bash
npx skills add prized-dev/skills
```

Then start a new session and ask your agent to run `python3 --version` in a Prized sandbox. It creates a sandbox, prints `Python 3.12.3` and deletes the sandbox.

The full guide is [Use Prized from your coding agent](https://prized.dev/docs/sandboxes-coding-agents).

## What the skill runs

The skill is instructions in [SKILL.md](skills/prized-sandboxes/SKILL.md) plus three helper scripts the agent can copy into your project (Python standard library, and TypeScript with only `fetch`). The plugin has no hooks, MCP servers or background processes.

When the agent follows it, it reads `PRIZED_API_KEY` from your environment and sends it only to Prized, at `api.prized.dev` and each sandbox's edge address (`term.prized.dev` today). It may install the `prized` CLI from `https://prized.dev/install.sh`. Each sandbox it creates bills to your Prized workspace per second while it runs, and the skill tells the agent to set a maximum runtime and delete every sandbox. Prices are on the [pricing page](https://prized.dev/pricing).

## Where the skill comes from

The skill is maintained with the Prized product and published at [prized.dev/SKILL.md](https://prized.dev/SKILL.md). A GitHub Action copies the published version into `skills/` every hour and checks it against the digest prized.dev lists, so this repo installs the same files as `npx skills add https://prized.dev`. Edits to `skills/` here are overwritten. For a fix or a request, open an issue or email team@prized.dev.

## License

[Apache-2.0](LICENSE)
