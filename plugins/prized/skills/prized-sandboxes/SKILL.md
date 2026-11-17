---
name: prized-sandboxes
description: Run code, shell commands, tests and coding agents in Prized Sandboxes, isolated Linux microVMs that start in seconds, bill per second and are deleted when the job is done, through the prized CLI (create, exec, cp, fork, pause, resume, ports). Use when the user wants to run untrusted, user-submitted or AI-generated code somewhere other than their machine, run tests or evals in clean throwaway machines or in N parallel copies, fan one setup out with fork, try something on a fresh Linux machine, give an agent its own short-lived VM, build sandboxes into their app with Prized's Python or TypeScript SDK, move code off E2B, or mentions Prized Sandboxes, prized.dev or `prized sandbox`.
compatibility: Needs the prized CLI v0.21.12 or later (macOS, Linux or Windows) signed in to a Prized account, and internet access to api.prized.dev.
metadata:
  homepage: https://prized.dev/sandboxes
  docs: https://prized.dev/docs/sandboxes.md
  pricing: https://prized.dev/pricing.md
  llms: https://prized.dev/llms.txt
---

# Prized Sandboxes

A sandbox is a Linux microVM (Ubuntu 24.04, user `prized`, no sudo) that starts from a template in seconds, runs commands and moves files, and is deleted when the job is done. It bills per second while it runs and only for storage while paused. It runs 24 hours by default and up to 7 days (60 minutes on the free tier), then it is deleted. The docs are the source of truth: https://prized.dev/llms.txt lists every page, and adding `.md` to a docs URL gives its Markdown.

## Rules

- Ask the user before you install the CLI, and before the first sandbox you start in a conversation: say the template, the size if not the default, and how long it may run. Sandboxes cost money.
- Give every sandbox `--max-runtime` for the job, and delete it when the job is done, even when the job failed (`prized sandbox rm <id> -y`). For several, give them one `--label run=<name>` and delete them together with `prized sandbox rm --label run=<name> -y`.
- Never print, log or commit a key, never put one on a command line, and never read `~/.config/prized`. Never pass the user's own secrets (their API keys, tokens, `.env` values) into a sandbox unless they ask you to, and then ask how.
- Act only on sandboxes you created in this conversation or the user named. `prized sandbox ls` shows every sandbox in the workspace, including other people's and their apps'.
- Quote prices only from https://prized.dev/pricing.md, read at the time, never from memory.
- Add `--json` to `prized` commands when you parse the output: each prints one JSON object with an `ok` field, and failures carry `error.code` and a `hint` to relay (codes: https://prized.dev/docs/cli.md#for-agents-and-scripts).

## 1. The CLI and the sign-in

Run `prized sandbox ls --json`.

- `prized` not found: ask the user to install the CLI themselves. Read https://prized.dev/docs/quickstart.md#2-install-the-cli and give them the exact install line for their system, ready to paste, and say they can run it in a terminal, or here by typing it after an exclamation mark, as `! <the line>`. Don't run the installer yourself. The installer adds the CLI to PATH for new terminals, not for this session: if `prized` is still not found, write it as the full path the installer printed (usually `~/.local/bin/prized`) in every command after, spelled out each time rather than kept in a shell variable, rather than starting commands with `export PATH=...`, which makes Claude Code ask about each one separately. Below v0.21.12, ask, then run `prized update`.
- It works: this machine is signed in. Keep that account and never run `prized login` over it.
- It fails with `AUTH`: ask whether the user has a Prized account. If they do, they run `prized login` in a terminal (or `! prized login` here) and tell you when it has finished. If they don't, ask for their email address and follow https://prized.dev/auth.md, its From a shell part: Prized emails them a 6-digit code, they give it to you, and the CLI saves the key without it showing in your output. A new account comes with free credit and no card.

The sign-in is shared with Prized boxes (the prized-boxes skill). A key made for Sandboxes only reaches sandboxes; if a box command is refused for that, say so.

## 2. One real run first

```bash
prized sandbox create --max-runtime 30m --json      # waits until it is running; read the id (sbx_...)
prized sandbox exec <id> -- python3 --version       # exits with the command's exit code
prized sandbox rm <id> -y
```

It prints `Python 3.12.3`. Do the user's job once this works.

## 3. Run the job

| What | Command |
| --- | --- |
| Start one | `prized sandbox create --max-runtime 1h [--template <t>] [--vcpu N] [--memory 16] [--disk 30] [--label run=<name>] --json` |
| Run a command | `prized sandbox exec <id> [--cwd <dir>] -- '<shell line>'` (5 minute timeout by default, `--timeout 1h` at most; exit 124 on a timeout) |
| A long job | `prized sandbox exec <id> --detach --keep-awake -- '<shell line>'` returns a process id; `--status <pid>`, `--logs <pid>`, `--follow <pid>`, `--ps`, `--kill <pid>` |
| Copy a file in or out | `prized sandbox cp ./data.csv <id>:data.csv`, `prized sandbox cp <id>:out/report.json ./report.json` |
| Parallel copies | `prized sandbox fork <id> --count 4 --label run=<name> --json` (from a running or paused sandbox; prints the copies' ids) |
| Reach a server in it | `prized sandbox port <id> 8000` prints its https URL; `--token` adds a short-lived token for a browser tab |
| A shell for the user | give them `prized sandbox ssh <id>` |
| Pause, resume | `prized sandbox pause <id>`, `prized sandbox resume <id>` (paused, it keeps memory and disk and bills only storage) |
| More time | `prized sandbox extend <id> --by 2h`, or `prized sandbox timeout <id> --in 30m` |
| What's running | `prized sandbox ls --label run=<name> --json`, `prized sandbox get <id> --json` (`expiresAt` is when it will be deleted) |

What agents get wrong:

- `exec` runs what follows `--` with `bash -c` in `/home/prized/work`, so pass a shell line as one quoted string. Paths are under `/home/prized`. There is no root, so no `apt`; `pip install` and `npm install -g` go to `~/.local`.
- A failed command is still a finished command: read its exit code and both stdout and stderr (many test runners report on stderr).
- A relative path, in `cp`'s `<id>:<path>` or in a command, is under `/home/prized/work`. Files move one at a time, up to 100 MB each. For a folder, `tar` it here, copy the archive in, and untar it with an `exec`. For a git project, cloning inside the sandbox is often simpler.
- Templates (`prized sandbox templates`): `prized-base-v1` (Python 3, Node 22, git, build tools; the default), `prized-agent-v1` (adds Claude Code and Codex, which need their own sign-in or key: ask the user how before you run an agent in it), and `prized-docker-v1` (adds Docker and Compose; needs a paid workspace, give it `--disk 30`).
- The free tier (free credit only) allows 2 vCPU and 4 GB per sandbox, 10 sandboxes and 60 minutes of running each. An error that says `"tier": "free"` is that limit, not a bug: tell the user a plan or a top-up lifts it, and never pick one or pay for them. Docker on free credit answers `template_needs_payment` the same way.
- A fork that doesn't fit answers `fork_capacity` with `fits`: fork that many or fewer.

## 4. From their own code

When the user wants their app, service or agent to create sandboxes itself, use the SDK: `pip install prized` (Python 3.10 or later) or `npm i @prized/sdk` (Node 18 or later), as https://prized.dev/docs/sandboxes-python-typescript.md shows.

```python
from prized import Sandbox

with Sandbox.create(max_runtime_min=30) as sb:           # deleted when the block ends
    sb.files.write("/home/prized/work/main.py", "print(6 * 7)")
    r = sb.exec("python3 main.py", timeout=120)
    print(r.exit_code, r.stdout)                           # 0 42
```

The app needs an API key of its own: the user makes one at https://prized.dev/dashboard/workspace/api-keys (Full access, or Custom with Sandboxes: Write) and puts it in the app's secret settings themselves. Don't ask them to paste it into this conversation. The plain HTTP API, every route and error: https://prized.dev/docs/sandboxes-api.md. Code written for E2B: https://prized.dev/docs/moving-from-e2b.md links a drop-in adapter for Python and TypeScript and says what works differently.

## When a box fits better

A sandbox is for a job with an end. A Prized box is a cloud Linux machine of the user's own, with sudo and no maximum run time, that keeps its disk and comes back when they do. Use the prized-boxes skill when Claude Code or another agent should keep working overnight or with the laptop closed, when the work needs sudo, apt or raw TCP, or when the user wants a dev machine to come back to. Boxes and sandboxes share one workspace and balance.

## References

- Sandboxes: https://prized.dev/docs/sandboxes.md
- Run an AI agent's commands in a microVM: https://prized.dev/docs/sandboxes-run-agent-code.md
- Fork a running VM to run work in parallel: https://prized.dev/docs/sandboxes-fork-parallel.md
- Docker and Compose in a sandbox: https://prized.dev/docs/sandboxes-docker.md
- CLI: `prized sandbox --help`, and `prized sandbox <command> --help`
