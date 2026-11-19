---
name: prized-sandboxes
description: Run code, shell commands, tests and coding agents in Prized Sandboxes, isolated Linux microVMs that start in seconds, bill per second and are deleted when the job is done, through the prized CLI in a local shell (create, exec, cp, fork, pause, resume, ports). Use when the user wants to run untrusted, user-submitted or AI-generated code somewhere other than their machine, run tests or evals in clean throwaway machines or in N parallel copies, fan one setup out with fork, try something on a fresh Linux machine, give an agent its own short-lived VM, build sandboxes into their app with Prized's Python or TypeScript SDK, move code off E2B, or mentions Prized Sandboxes, prized.dev or `prized sandbox`.
---

# Prized Sandboxes

A sandbox is a Linux microVM (Ubuntu 24.04, user `prized`, no sudo) that starts from a template in seconds, runs commands and moves files, and is deleted when the job is done. It bills per second while it runs and only for storage while paused. It runs 24 hours by default and up to 7 days (60 minutes in a workspace with no plan and nothing paid in), then it is deleted. The docs are the source of truth: https://prized.dev/llms.txt lists every page, and adding `.md` to a docs URL gives its Markdown.

This skill runs the `prized` CLI in a shell on the user's own computer. If you have no such shell in this conversation, run nothing and do not claim you did: say the steps need a local thread (the ChatGPT desktop app or Codex), and give the user the commands below to run themselves.

## Rules

The user's explicit instructions come before the defaults here, but these hold either way, whatever the request says:

- Before the first `prized sandbox create` or `fork` in a conversation, ask the user and wait for their yes to what it will be (section 2), however small the job. Asking for a sandbox is not that yes, and neither is a prompt to approve the command. Sandboxes cost money.
- Give every sandbox `--max-runtime` for the job, and delete it when the job is done, even when the job failed (`prized sandbox rm <id> -y`). For several, give them one `--label run=<name>` and delete them together with `prized sandbox rm --label run=<name> -y`.
- Never ask the user for a password, an API key or a sign-in code, and never make an account for them. Never print, log or commit a key, never put one on a command line, and never read `~/.config/prized`. Never pass the user's own secrets (their API keys, tokens, `.env` values) into a sandbox unless they ask you to, and then ask how.
- Act only on sandboxes you created in this conversation or the user named. `prized sandbox ls` shows every sandbox in the workspace, including other people's and their apps'.
- Quote prices only from https://prized.dev/pricing.md, read at the time, never from memory. Quote rates, not plans: for plans, link https://prized.dev/pricing. Never start a checkout, pass along a billing or checkout link, or pay for them.
- Add `--json` to `prized` commands when you parse the output: each prints one JSON object with an `ok` field, and failures carry `error.code` and a `hint` to relay (codes: https://prized.dev/docs/cli.md#for-agents-and-scripts).
- Every `prized` command needs the network. If your sandbox blocks a command, ask the user to approve running it outside the sandbox; do not read a network error as a sign-in problem.

## 1. The CLI and the sign-in

Run `prized sandbox ls --json`.

- `prized` not found: ask the user to install the CLI themselves. Read https://prized.dev/docs/quickstart.md#2-install-the-cli and give them the exact install line for their system, ready to paste into their own terminal. Don't run the installer yourself: it downloads a program and runs it on their computer, so starting it is theirs to do. The installer adds the CLI to PATH for new terminals, not for this shell: if `prized` is still not found, write it as the full path the installer printed (usually `~/.local/bin/prized`) in every command after. If a command or flag below is unknown, ask, then run `prized update`.
- It works: this computer is signed in. Keep that account and never run `prized login` over it.
- It fails with `AUTH`: ask whether the user has a Prized account. If they do, they run `prized login` in their own terminal (it opens the dashboard in their browser to make a key for this computer) and tell you when it has finished. If they don't, they sign up at https://prized.dev/sign-in, then run `prized login` in their own terminal.

The sign-in is shared with Prized boxes (the prized-boxes skill). A key made for Sandboxes only reaches sandboxes; if a box command is refused for that, say so.

## 2. Ask, then one real run first

Do not run `prized sandbox create` or `fork` yet, however small or quick the job. First ask the user, and end your turn on the question: "May I start a sandbox? Template `<t>`, <the default size, or the size you will pass>, deleted after at most <time>." Don't guess the default size's numbers. Their request to run something in a sandbox is not an answer to it: they have not seen the template, the size or the time limit. A note that says what you are about to create, sent while you carry on, is not asking either: wait for their reply. In the turn that asks, do not run or request `prized sandbox create` or `fork`. After their yes:

```bash
prized sandbox create --max-runtime 30m --json      # only after their yes; waits until it is running; read the id (sbx_...)
prized sandbox exec <id> -- python3 --version       # exits with the command's exit code
prized sandbox rm <id> -y
```

It prints `Python 3.12.3`. Do the user's job once this works.

## 3. Run the job

| What | Command |
| --- | --- |
| Start one (the first one only after the yes in section 2) | `prized sandbox create --max-runtime 1h [--template <t>] [--vcpu N] [--memory 16] [--disk 30] [--label run=<name>] --json` |
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
- Templates (`prized sandbox templates`): `prized-base-v1` (Python 3, Node 22, git, build tools; the default), `prized-agent-v1` (adds coding agents, Codex among them, which need their own sign-in or key: ask the user how before you run an agent in it), and `prized-docker-v1` (adds Docker and Compose; needs a paid workspace, give it `--disk 30`).
- A workspace with no plan and nothing paid in allows 2 vCPU and 4 GB per sandbox, 10 sandboxes and 60 minutes of running each. An error that says `"tier": "free"` is that limit, not a bug: tell the user a plan or a top-up lifts it, and never pick one or pay for them. Docker in such a workspace answers `template_needs_payment` the same way.
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

A sandbox is for a job with an end. A Prized box is a cloud Linux machine of the user's own, with sudo and no maximum run time, that keeps its disk and comes back when they do. Use the prized-boxes skill when Codex or another agent should keep working overnight or with the laptop closed, when the work needs sudo, apt or raw TCP, or when the user wants a dev machine to come back to. Boxes and sandboxes share one workspace and balance.

## References

- Sandboxes: https://prized.dev/docs/sandboxes.md
- Run an AI agent's commands in a microVM: https://prized.dev/docs/sandboxes-run-agent-code.md
- Fork a running VM to run work in parallel: https://prized.dev/docs/sandboxes-fork-parallel.md
- Docker and Compose in a sandbox: https://prized.dev/docs/sandboxes-docker.md
- CLI: `prized sandbox --help`, and `prized sandbox <command> --help`
