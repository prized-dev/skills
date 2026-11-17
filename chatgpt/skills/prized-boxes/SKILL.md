---
name: prized-boxes
description: Put the user's project on a Prized box, a cloud Linux dev machine where Codex and long jobs keep running with the laptop closed, using the prized CLI in a local shell. Use when the user wants a coding agent to keep working overnight or after they close the laptop, wants a cloud dev box or a remote machine for their agents, wants a long build, test run or eval to run somewhere else, or asks to check on, pause, resume or resize a Prized box.
---

# Prized boxes

A box is a cloud Linux machine of the user's own from Prized (https://prized.dev): sudo, its own disk, no maximum run time. Codex runs on it in a tmux session that keeps going when the laptop sleeps, and the user looks in from a terminal, a browser or the ChatGPT app. A box bills by the hour while awake and only for its disk while paused. The docs are the source of truth: https://prized.dev/llms.txt lists every page, and adding `.md` to a docs URL gives its Markdown.

This skill runs the `prized` CLI in a shell on the user's own computer. If you have no such shell in this conversation, run nothing and do not claim you did: say the steps need a local thread (the ChatGPT desktop app or Codex), and give the user the commands below to run themselves.

## Rules

The user's explicit instructions come before the defaults here. These hold either way:

- Ask the user before you install the CLI, create or resize a box (both cost money), copy the project, or copy any credential. Pass only the flags they said yes to.
- Copy, never move or delete their files. The project goes to the box once, one way (`--copy-once`). Start a sync only if they ask for one.
- Never ask the user for a password, an API key or a sign-in code, and never make an account for them. Never run `prized login` yourself, and never switch the account this computer uses.
- Never print, log or commit a key, never put one on a command line, and never read `~/.config/prized`.
- Act only on the box the user named. Never pause, resize or delete a box they did not ask about.
- Do not quote prices or pick a plan. For rates, point the user to https://prized.dev/pricing. Never start a checkout or pay for them.
- Add `--json` to `prized` commands: each prints one JSON object with an `ok` field, and failures carry `error.code` and a `hint` to relay (codes: https://prized.dev/docs/cli.md#for-agents-and-scripts).
- `prized box new --wait` and `prized setup` can take several minutes: give them a 10 minute timeout. They need the network and write outside this folder; if your sandbox blocks them, ask the user to approve running them outside it.

## 1. Install the CLI

If `prized version` fails, ask, then run `curl -fsSL https://prized.dev/install.sh | sh` (Windows: `powershell -c "irm https://prized.dev/install.ps1 | iex"`). If `prized` is still not found, use the path the installer printed. If a command or flag below is unknown, ask, then run `prized update`.

## 2. Sign in

Run `prized box ls --json`. If it works, this computer is signed in: keep that account. If it fails with `AUTH`, ask whether the user has a Prized account.

- They do: ask them to run `prized login` in their own terminal (it opens the dashboard in their browser to make a key for this computer) and to tell you when it has finished.
- They don't: they sign up at https://prized.dev/sign-in, then run `prized login` in their own terminal.

Then run `prized box ls --json` again. If it fails with any other code, tell the user what it says.

## 3. A box

`prized box ls --json` lists their boxes with `hostname`, `observedState`, `tier` (its size) and `autoPauseMin`. If there is none, ask, then run `prized box new --wait --json`. Add `--size <size>` only for the size the user picked. Sizes, smallest first: Nano (`nano`), Micro (`micro`), Extra Small (`lite`), Small (`flow`), Medium (`pro`), Large (`max`), Extra Large (`ultra`). If the account cannot run a size, the CLI refuses with a hint: relay it.

With several boxes, ask which one, then name it in every command after: as the argument where a command below shows `<box>`, and as `--box <name>` everywhere else (`prized exec --box <name> --cwd ... -- ...`, `prized setup`, `prized status`).

## 4. Copy the project onto it

Add `--no-advisor` to every `prized setup` and `prized env` command: otherwise setup sends the project's manifests (README, Makefile, package.json and the like, secrets redacted) to Prized's advisor to tailor its questions.

1. Run `prized setup --dry-run --json --non-interactive --no-advisor --copy-once .` in the project. It changes nothing, and its `login` step names the account. If it refuses this folder (exit 2), use `--no-project` in place of `--copy-once .`.
2. Ask in one message: may you copy this project to the box once, with no sync (name the account and the box)? Copy Codex's settings and MCP servers there (`--agent codex`)? Their GitHub CLI token and git identity (`--gh`)? For their toolchain, run `prized env plan --json --no-advisor` and read them the groups; the ones they pick go in `--env <groups>`. Never copy a home folder, the Desktop or a folder inside `~/Prized`.
3. Run setup once, with a flag for every answer: `--agent codex` or `--no-agents`, `--gh` or `--no-gh`, `--env <groups>` or `--no-env`. For example, a yes to the copy and no to the rest is `prized setup --json --non-interactive --no-advisor --copy-once . --no-agents --no-gh --no-env`. It copies the project to `~/code/<folder>` on the box (`.git` included; `node_modules`, virtualenvs, build caches and `.env` files stay here). Before running the project's tests there, install its dependencies on the box: `--env node` or `--env python` does it from a lockfile, or run the install with `prized exec`.
4. Read `steps[]` in the JSON: each step has a `status` of `done`, `skipped` or `failed` and a `detail`. The `project` step's detail names the folder on the box; a `failed` one carries a hint to relay. A ChatGPT sign-in never travels to the box. If the agents step reports codex as `manual`, Codex is not signed in on the box: the user runs `prized agents handoff codex` in their own terminal (it opens the sign-in page in their browser), or `prized ssh`, then `codex login --device-auth` on the box, once.

To work on the box from the ChatGPT desktop app on a Mac, the user opens Settings > Connections, clicks Add under SSH connections from this Mac, and ticks the box; projects are in `~/code` (https://prized.dev/docs/codex.md).

## 5. Run Codex or a long job there

| What | Command |
| --- | --- |
| Run one command in the project | `prized exec --cwd code/<folder> -- npm test` |
| A long job that outlives this session | `prized exec --detach --keep-awake --cwd code/<folder> -- ./long-job.sh` (returns a `processId`; the box stays awake until the job exits) |
| Hand Codex a task and walk away | `prized prompt --provider codex --cwd code/<folder> --detach "<the task>"` (headless `codex exec` on the box; `--auto` turns off approvals and the sandbox, so add it only on the user's yes) |
| Codex in a session they open themselves | give them `prized agents run codex --attach --dir code/<folder>`; they reattach later with `prized ssh -s codex` |

`--detach` runs return at once, and closing the laptop leaves them running. `prized exec` runs what follows `--` under `sh -c` in the box's home folder, so pass a shell line as one quoted string. `prized prompt` needs Codex signed in on the box (step 4); without `--auto` it runs in Codex's `workspace-write` sandbox, which edits and runs commands in the project with no network. If `--keep-awake` is refused (an older box agent), ask, then run `prized box auto-pause <box> off` and start the job without it.

## 6. Check on it

- `prized box ls --json`: every box and its `observedState` (`running`, `suspending`, `suspended` and the rest). A box paused over 3 days is in deep sleep: it wakes in a minute or two with its processes restarted. `prized box info <box> --json` adds its last events.
- `prized exec --ps --json` lists detached jobs; `prized exec --status <processId> --json` shows one's state, exit code and the tails of `stdout` and `stderr` (read both: many test runners report on stderr).
- `prized prompt ls --json` lists prompt runs; `prized events --json` shows the newest run's events, and `prized events --follow` follows it live. These do not wake a paused box.
- `prized status --json`: the box, its sync and ports from this computer's view.

## 7. Pause, resume and resize

- `prized box pause <box> --json`: compute stops, the disk stays, billing drops to the asleep rate. `prized box ls --json` shows `observedState` `suspended` once it has finished. Nano through Small keep their running processes through a pause; Medium and up restart them.
- `prized box resume <box> --wait --json` wakes it. `prized ssh`, `prized exec` and `prized prompt` also wake a paused box.
- Auto-pause: a box pauses itself after sitting idle for its window. Set it with `prized box auto-pause <box> 2h` (30m to 7d) or `off`. Some accounts cap the window at 12 hours, and the CLI says so. Codex printing in its session, a `prized prompt` run and a `--keep-awake` job count as use.
- Resize, only on the user's yes, since it changes what the box costs: `prized box resize <box> <size> --json`. The box restarts at the new size with its files intact, so running processes stop. Disks grow with a bigger size and never shrink. A refusal exits 5 with a hint: relay it.

## 8. Delete, only when asked

`prized box delete <box> -y --json` deletes the machine and its disk. For 7 days its last state can usually be restored. Confirm the box's name with the user first.
