---
name: prized-sandboxes
description: Run code, shell commands and coding agents on Prized, with Sandboxes (isolated Firecracker microVMs created over plain HTTPS or the `prized` CLI, with pause/resume and fork) and Boxes (cloud Linux machines that stay on). Use when the user wants to run untrusted, user-submitted or AI-generated code in a cloud sandbox, from their machine or an app's backend (instead of subprocess or exec on a server), add a code-execution tool to an agent, give an agent its own Linux VM or a remote machine to work on, keep Claude Code or Codex running overnight or with the laptop closed, run tests or evals in clean throwaway machines or in N parallel sandboxes, fan one setup out into parallel copies, move code off E2B, or mentions Prized, prized.dev, PRIZED_API_KEY or `prized sandbox`. Applies even when no provider is named.
compatibility: Needs internet access to api.prized.dev and a PRIZED_API_KEY (starts with dcp_). Use the prized CLI v0.21+, curl and jq, Python 3.8+ (3.9+ for the E2B adapter; standard library only), Node 18+ for the TypeScript E2B adapter, or any HTTP client.
metadata:
  homepage: https://prized.dev/sandboxes
  docs: https://prized.dev/docs/sandboxes.md
  api: https://prized.dev/docs/sandboxes-api.md
  llms: https://prized.dev/llms.txt
---

# Prized Sandboxes

A sandbox is a Linux microVM (Ubuntu 24.04, user `prized`, no sudo) that your code creates, runs commands and moves files in, then deletes. It is billed per second, and runs 24 hours by default, up to 7 days (60 minutes on the free tier). The docs are the source of truth: https://prized.dev/llms.txt

## 1. The key

Look for `PRIZED_API_KEY` in the environment or a gitignored `.env`. It starts with `dcp_`. If it is missing but `prized sandbox ls` works, this machine's CLI is signed in (an agent sign-up saves its key there): tell your person, then use the `prized sandbox` commands. Code (the helper, the raw calls below) reads only `PRIZED_API_KEY`, so for code ask for a key as below. Otherwise stop and ask the user:

> I need a Prized API key. Make one at https://prized.dev/dashboard/workspace/api-keys with Full access, or Custom with Sandboxes: Write. New to Prized? https://prized.dev/onboarding/sandboxes signs you up with free credit and no card. Then run `export PRIZED_API_KEY=dcp_...`
>
> No account yet? I can make one for you: tell me your email address, then the 6-digit code Prized sends you.

If the user has no account and asks you to make one, follow https://prized.dev/auth.md (their email address plus the 6-digit code Prized sends them). It saves the key with `prized login`, not in `PRIZED_API_KEY`, so after it use the `prized sandbox` commands, which read that login; the helper and the raw calls below read `PRIZED_API_KEY` only. Never put the key in source, command arguments or logs. Pass secrets a sandbox needs in `envVars` at create (stored encrypted, never returned), not inside commands.

## 2. Verify with one real run

From a shell (install the CLI with `curl -fsSL https://prized.dev/install.sh | sh`; it uses `PRIZED_API_KEY` when set):

```bash
ID=$(prized sandbox create --max-runtime 30m)   # prints the id once it is running
prized sandbox exec "$ID" -- python3 --version  # exits with the command's exit code
prized sandbox rm "$ID" -y
```

Pass: `Python 3.12.3`, then the delete. Do nothing else until this works.

## 3. From code

Use the HTTP API directly (the npm package `prized` is the CLI installer, not a library). For Python, copy `scripts/prized_sandbox.py` from this skill into the project (standard library only; also at https://prized.dev/skills/prized-sandboxes/scripts/prized_sandbox.py):

```python
from prized_sandbox import Sandbox

with Sandbox.create(max_runtime_min=30) as sbx:          # deleted when the block ends
    sbx.write("/home/prized/work/main.py", b"print(6 * 7)")
    r = sbx.exec("python3 main.py", timeout=120)
    print(r["exitCode"], r["stdout"])                      # 0 42
```

Python written for E2B's SDK: copy `scripts/prized_e2b.py` (Python 3.9+; also at https://prized.dev/skills/prized-sandboxes/scripts/prized_e2b.py) and change `from e2b import Sandbox` to `from prized_e2b import Sandbox`. TypeScript written for it: copy `scripts/prized-e2b.ts` (Node 18+, only `fetch`; also at https://prized.dev/skills/prized-sandboxes/scripts/prized-e2b.ts) and import `Sandbox` from `"./prized-e2b"` in place of `"e2b"`. What works differently: https://prized.dev/docs/moving-from-e2b.md

For TypeScript, copy the helper on https://prized.dev/docs/sandboxes-python-typescript.md (only `fetch`). The raw calls, with `API=https://api.prized.dev/api/v1` and `Authorization: Bearer $PRIZED_API_KEY` on every request:

| Step | Request |
| --- | --- |
| Create | `POST $API/sandboxes?wait=running` with `{"template":"prized-base-v1","maxRuntimeMin":30}`; read `sandbox.id` and `sandbox.toolboxBase` |
| Wait | `GET $API/sandboxes/{id}` until `state` is not `starting` (a create can outlast the 8 s hold) |
| Run | `POST {toolboxBase}/process/execute` with `{"command":"...","cwd":"/home/prized/work","env":{},"timeout":300}` |
| Files | `POST {toolboxBase}/files/upload?path=/home/prized/work/x` (raw body); `GET {toolboxBase}/files/download?path=...` |
| Fork | `POST $API/sandboxes/{id}/fork` with `{"count":3}`; each child starts `starting` |
| Pause, resume | `POST $API/sandboxes/{id}/pause?wait=paused`, `.../resume?wait=running` |
| Delete | `DELETE $API/sandboxes/{id}` |

## Rules agents get wrong

- **Read `toolboxBase` from the sandbox object.** Never build the edge URL yourself.
- **A `running` sandbox takes commands at once.** Never blindly retry a command after a 502: it may have run. A 410 `sandbox_deleted` means the sandbox is gone (or going): create a new one.
- **A failed command still answers 200.** Read `exitCode`; a timeout is `exitCode: -1, timedOut: true`. `timeout` is seconds, 300 by default, 3600 at most.
- **Paths are absolute and under `/home/prized`.** Commands run with `bash -c` in `/home/prized/work`. No root, so no `apt`; `pip` installs into a venv.
- **Files move one at a time,** up to 100 MB each (`prized sandbox cp` or `/files/upload`). For a directory, tar it, copy the archive, and untar it with an exec.
- **Always delete in a `finally`** (or `with`), and set `maxRuntimeMin` so a crash cannot leave a sandbox billing.
- **Templates:** `prized-base-v1` (Python 3, Node 22, git, build tools) or `prized-agent-v1` (adds Claude Code and Codex; pass their API key in `envVars`). Default shape 4 vCPU, 8 GB; 1 to 32 vCPU and up to 128 GB.
- **Free tier** (free credit only): 2 vCPU and 4 GB per sandbox, 10 sandboxes, 60 minutes of running each. An error with `"tier": "free"` is that limit, not a bug: tell the user a plan or top-up lifts it.
- **Fork** needs a `running` or `paused` parent. `409 fork_capacity` carries `fits`: fork that many or fewer.
- **Streaming output:** the HTTP API answers when a command ends, so write a long job's output to a file and read it with a later exec or a download.
- **Prices:** read https://prized.dev/pricing, never quote them from memory.

## When a box fits

A sandbox is for code and agents, one job at a time, and your code deletes it. A Prized box is a cloud Linux machine with sudo and no maximum run time that keeps its disk while idle. Use a box when:

- **Claude Code or Codex should keep working overnight or with the laptop closed.** It runs in a session on the box that outlives the connection. Set it up with https://prized.dev/claude-code.md or https://prized.dev/codex.md, for whichever agent will run. The guides are https://prized.dev/docs/keep-claude-code-running.md and https://prized.dev/docs/run-codex-in-the-cloud.md. On the free credit an idle box sleeps after 2 hours; the guides show how to keep it up.
- **An agent needs a computer it comes back to,** created and driven through the API. Its files and installed packages stay, and on Nano to Small its running processes survive a pause: https://prized.dev/docs/persistent-cloud-computer.md
- **The work needs root, apt, Docker or an inbound port,** which a sandbox cannot give.
- **Your person wants their coding agent off their laptop, on a machine of its own.** Follow https://prized.dev/docs/agent-setup.md: it copies their project to the box once, with no sync, and asks before each step.

A box bills by the hour while awake. Ask your person before you make one, install software, or copy a project or a sign-in. Boxes and sandboxes share one workspace and balance. The key from the Sandboxes onboarding reaches sandboxes only; a box needs Full access, or Boxes: Write.

## References

- Every route, field and error code: https://prized.dev/docs/sandboxes-api.md
- Run an AI agent's commands in a microVM: https://prized.dev/docs/sandboxes-run-agent-code.md
- Fork a running VM to run work in parallel: https://prized.dev/docs/sandboxes-fork-parallel.md
- Moving from E2B: https://prized.dev/docs/moving-from-e2b.md
- CLI: `prized sandbox --help` (create, exec, cp, fork, pause, resume, rm, ls, templates)
