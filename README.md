# Prized for Claude Code

Give your coding agent its own Linux computers. This plugin lets Claude Code create [Prized Sandboxes](https://prized.dev/sandboxes) (Firecracker microVMs that start in seconds), run commands in them, move files between them and your machine, fork one into live copies with its memory and running processes, pause them and delete them. The same repository is a plugin marketplace for Codex and a skill for Cursor and other agents.

## Install

You need Node.js 20 or later, which runs the plugin's MCP server. In Claude Code (v2.1.275 or later):

```text
/plugin install prized --marketplace prized-dev/skills
```

It asks for your Prized API key and keeps it in your system's credential store. Make one with Full access, or Custom with Sandboxes: Write, on the [API keys page](https://prized.dev/dashboard/workspace/api-keys). New to Prized? [Sandboxes onboarding](https://prized.dev/onboarding/sandboxes) signs you up with free credit and no card. If `PRIZED_API_KEY` is already exported in the shell you start Claude Code from, leave the field as it is. To change the key later, run `/plugin`, open Prized on the Installed tab and choose Configure options.

From your shell, `claude plugin install prized --marketplace prized-dev/skills` (v2.1.292 or later) installs it without asking for the key: export `PRIZED_API_KEY`, or set the key with Configure options as above. On older versions, run `/plugin marketplace add prized-dev/skills`, then `/plugin install prized@prized`.

Then run `/prized:sandboxes`, or ask Claude to use the Prized sandbox tools to run `python3 --version`.

## Commands

| Command | What it does | What it costs |
| --- | --- | --- |
| `/prized:fork [copies] <what to try>` | Sets your project up once in a sandbox, forks it into live copies (3 by default), tries a different approach in each, runs your check in all of them at once, brings the winning change back and deletes every sandbox. | 2 vCPU and 4 GB per sandbox at $0.131 an hour, so a parent and 3 copies for 10 minutes is about 9 cents. |
| `/prized:offload <job>` | Copies your project to a sandbox and runs a long job there (a test suite, build, eval or script) that keeps going when your laptop sleeps or you quit Claude Code. `/prized:offload status` checks on it and brings results back. | 4 vCPU and 8 GB at $0.261 an hour until the sandbox is deleted (finishing the job doesn't stop it), and never past the run time it sets. |
| `/prized:sandboxes [clean]` | Lists the sandboxes in your workspace with what each costs. `clean` finds what these commands left behind (finished jobs, leftover fork copies) and deletes what you confirm. | Free. |

Sandboxes bill per second from your Prized balance; a paused sandbox bills only storage. On free credit each sandbox gets 2 vCPU and 4 GB for up to 60 minutes. Prices are on the [pricing page](https://prized.dev/pricing).

## What the plugin adds and runs

- **The `prized-sandboxes` skill**, instructions Claude loads when a task calls for a sandbox ([SKILL.md](skills/prized-sandboxes/SKILL.md)), with three helper scripts it can copy into your project (Python standard library, and TypeScript with only `fetch`).
- **The Prized Sandboxes MCP server**, [`@prized/sandbox-mcp`](https://www.npmjs.com/package/@prized/sandbox-mcp), with 11 tools: create, run a command, write and read a file, upload and download, list, fork, pause, resume and delete. Claude Code starts it with `npx -y @prized/sandbox-mcp@0.1.0`, which downloads that version and its dependencies from npm the first time, and runs it on your machine while a session is open. It reads your key from the plugin's settings (or `PRIZED_API_KEY`) and sends it only to Prized, at `api.prized.dev` and each sandbox's own address. `upload` and `download` reach only the folder Claude Code runs in, and are off when that is your home folder or `/`. Sandboxes it creates pause after 15 idle minutes by default and carry the label `created-by=prized-sandbox-mcp`.
- **Three commands**, the prompts in [`commands/`](commands). Each says what it will cost before it starts.

The plugin has no hooks and nothing else runs in the background. When Claude follows the skill, it may install the `prized` CLI from `https://prized.dev/install.sh`.

## Codex, Cursor and other agents

In Codex, the same marketplace installs the skill:

```bash
codex plugin marketplace add prized-dev/skills
codex plugin add prized@prized
```

For Cursor and other agents, install the skill with the `skills` CLI, which asks which agents get it:

```bash
npx skills add prized-dev/skills
```

These read `PRIZED_API_KEY` from the shell you start your agent from. The full guide is [Use Prized from your coding agent](https://prized.dev/docs/sandboxes-coding-agents).

## Where the skill comes from

The skill is maintained with the Prized product and published at [prized.dev/SKILL.md](https://prized.dev/SKILL.md). A GitHub Action copies the published version into `skills/` every hour and checks it against the digest prized.dev lists, so this repo installs the same files as `npx skills add https://prized.dev`. Edits to `skills/` here are overwritten. For a fix or a request, open an issue or email team@prized.dev.

## License

[Apache-2.0](LICENSE)
