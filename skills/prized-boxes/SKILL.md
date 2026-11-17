---
name: prized-boxes
description: Put the user's project on a Prized box, a cloud Linux dev machine where Claude Code, Codex and long jobs keep running with the laptop closed, driven by the prized CLI. Use when the user wants Claude Code or another coding agent to keep working overnight or after they close the laptop, wants a cloud dev box or a remote machine for their agents, asks to move this project or this conversation to the cloud, wants a long build, test run or eval to run somewhere else, or asks to check on, pause, resume or price a Prized box.
compatibility: Needs the prized CLI v0.21.12 or later (macOS, Linux or Windows), a Prized account, and internet access to api.prized.dev.
metadata:
  homepage: https://prized.dev
  docs: https://prized.dev/docs/boxes.md
  pricing: https://prized.dev/pricing.md
  llms: https://prized.dev/llms.txt
---

# Prized boxes

A box is a cloud Linux machine of the user's own (sudo, its own disk, no maximum run time). Claude Code runs on it in a tmux session that keeps going when the laptop sleeps, and the user looks in from a terminal, a browser or their phone. A box bills by the hour while awake and only for its disk while paused. The docs are the source of truth: https://prized.dev/llms.txt lists every page, and adding `.md` to a docs URL gives its Markdown.

## Rules

- Ask the user before you install the CLI, create or resize a box (both cost money), copy the project, or copy any credential. Pass only the flags they said yes to.
- Copy, never move or delete their files. The project goes to the box once, one way (`--copy-once`). Start a sync only if they ask for one.
- Never run `prized login` over a sign-in that works, and never switch the account this machine uses.
- Never print, log or commit a key, never put one on a command line, and never read `~/.config/prized`.
- Act only on the box the user named. Never pause, resize or delete a box they did not ask about.
- Quote prices only from https://prized.dev/pricing.md, read at the time, never from memory.
- Add `--json` to `prized` commands: each prints one JSON object with an `ok` field, and failures carry `error.code` and a `hint` to relay (codes: https://prized.dev/docs/cli.md#for-agents-and-scripts).
- `prized box new --wait` and `prized setup` can take several minutes: give them a 10 minute timeout. If your sandbox blocks the network, ask the user to approve running them outside it.

## The key, and where it goes

The CLI signs in with a Prized API key. `prized login` (the user, in a browser) or the email sign-up at https://prized.dev/auth.md saves it under `~/.config/prized`; if `PRIZED_API_KEY` is set in the shell, every `prized` command uses that key instead. The CLI sends the key to Prized's API at `api.prized.dev`. You never handle the key yourself. A key made for Sandboxes only cannot create boxes: boxes need Full access or Boxes: Write. If a box command is refused for that reason, tell the user rather than unsetting the variable.

## 1. Install the CLI

If `prized version` fails, ask, then run `curl -fsSL https://prized.dev/install.sh | sh` (Windows: `powershell -c "irm https://prized.dev/install.ps1 | iex"`). The installer adds the CLI to PATH for new terminals, not for this session: if `prized` is still not found, write it as the full path the installer printed (usually `~/.local/bin/prized`) in every command after. Don't start commands with `export PATH=...`: Claude Code then asks the user to approve each one separately, with no way to say yes once. Below v0.21.12, ask, then run `prized update`.

## 2. Sign in

Run `prized box ls --json`. If it works, this machine is signed in: keep that account. If it fails with `AUTH`, ask whether the user has a Prized account.

- They do: ask them to run `prized login` in another terminal and to tell you when it has finished.
- They don't: ask for their email address and follow https://prized.dev/auth.md, its From a shell part. Prized emails them a 6-digit code, they give it to you, and the key is saved for the CLI without showing in your output. A new account usually comes with free credit, no card.

## 3. A box

`prized box ls --json` lists their boxes. If there is none, or they want a new one, ask in one message which size (with its price from the pricing page) and how long it may sit idle before it pauses itself, then run `prized box new <name> --size <size> --auto-pause <window> --wait --json`. Offer an auto-pause window (30m to 7d, 2h is a good default): without it, a box outside the free credit can start with auto-pause off and bill by the hour until someone pauses it. Without `--size`, Prized picks a size the balance runs comfortably. On the free credit it is one box at a time; bigger sizes need a plan (https://prized.dev/dashboard/billing). Sizes, smallest first: `nano`, `micro`, `lite`, `flow` (Small), `pro`, `max`, `ultra`. With several boxes, ask which one, then name it in every command after: as the argument where a command below shows `<box>`, and as `--box <name>` before the `--` everywhere else (`prized exec --box <name> --cwd ... -- ...`, `prized setup`, `prized status`).

## 4. Move the project onto it

Add `--no-advisor` to every `prized setup` and `prized env` command: otherwise setup sends the project's manifests (README, Makefile, package.json and the like, secrets redacted) to Prized's advisor to tailor its questions.

1. Run `prized setup --dry-run --json --non-interactive --no-advisor --copy-once .` in the project. It changes nothing, and its `login` step names the account. (`prized version` saying the daemon is not running is fine: setup starts it.) If it refuses this folder (exit 2), use `--no-project` in place of `--copy-once .`.
2. Ask in one message: may you copy this project to the box once, with no sync (name the account and the box)? Copy Claude Code's sign-in, MCP servers and settings there (`--agent claude`)? Their GitHub CLI token and git identity (`--gh`)? For their toolchain, run `prized env plan --json --no-advisor` and read them the groups; the ones they pick go in `--env <groups>`. Its output is long: the groups are `plan.groups[]`, each with `group` (the name for `--env`) and `question`. Put each of these to them as its own choice, even when the task is only to run tests: don't answer any of them for the user. Say that Claude Code's sign-in is what lets Claude Code keep working on the box with their laptop closed. Never copy a home folder, the Desktop or a folder inside `~/Prized`.
3. Run setup once, with a flag for every answer: `--agent claude` or `--no-agents`, `--gh` or `--no-gh`, `--env <groups>` or `--no-env`. For example, a yes to the copy and no to the rest is `prized setup --json --non-interactive --no-advisor --copy-once . --no-agents --no-gh --no-env`. It copies the project to `~/code/<folder>` on the box (`.git` included; `node_modules`, virtualenvs and build caches stay here). The project's `.env` files go only with `--env-secrets`, its own yes. Before running the project's tests there, install its dependencies on the box: `--env node` or `--env python` does it from a lockfile, or run the install with `prized exec`.
4. Read `steps[]` in the JSON: each step has a `status` of `done`, `skipped` or `failed` and a `detail`. The `project` step's detail names the folder on the box; a `failed` one carries a hint to relay. If the agents step reports claude as `manual`, Claude Code is not signed in on the box: the user runs `prized ssh`, then `claude`, then `/login`, once.

Already deep in a conversation they want to keep? The user can move this Claude Code conversation itself, mid-task, by typing `! prized teleport -y` in this session (Esc first if you are mid-step). It needs a box and `prized` v0.21.12, and it sets up a two-way sync of this folder with the box if there is none, so tell the user that first. If Claude Code is not signed in on the box, run `prized agents handoff claude` first, on their yes. `prized teleport back` brings it home. You do not run teleport yourself. Guide: https://prized.dev/docs/move-claude-code-to-the-cloud.md

## 5. Run the agent or a long job there

| What | Command |
| --- | --- |
| Run one command in the project | `prized exec --cwd code/<folder> -- npm test` |
| A long job that outlives this session | `prized exec --detach --keep-awake --cwd code/<folder> -- ./long-job.sh` (returns a `processId`; auto-pause waits for the job to exit) |
| Hand Claude Code a task and walk away | `prized prompt --provider claude --cwd code/<folder> --detach "<the task>"` (headless `claude -p` on the box; `--auto` skips approvals, so add it only on the user's yes) |
| Claude Code in a session they open themselves | give them `prized agents run claude --attach --dir code/<folder>`; they reattach later with `prized ssh -s claude` |

When the user asks for work to go on while they're away, overnight or with the laptop closed, it has to run on the box: a `prized prompt` run, a session they open, or a detached job. Doing the work from this session with `prized exec` stops when this session does, so don't do that and call it handed off. If Claude Code isn't signed in on the box, ask which they want: you copy this machine's sign-in (`prized agents handoff claude --box <box>`), or they sign in themselves (`prized ssh <box>`, then `claude`, then `/login`, once).

`--detach` runs return at once, and closing the laptop leaves them running. `prized exec` runs what follows `--` under `sh -c` in the box's home folder, so pass a shell line as one quoted string. `prized prompt` needs Claude Code signed in on the box (step 4); without `--auto`, Claude Code there may edit files but not run commands. If `--keep-awake` is refused (an older box agent), ask, then run `prized box auto-pause <box> off` and start the job without it.

## 6. Check on it

- `prized box ls --json`: every box, with `hostname`, `observedState` (`running`, `suspending`, `suspended`, `deep_sleep` for a box paused over 3 days, which wakes in a minute or two with its processes restarted), `tier` (its size) and `autoPauseMin`. `prized box info <box> --json` adds its last events.
- `prized exec --ps --json` lists detached jobs; `prized exec --status <processId> --json` shows one's `running`, `exitCode`, and the tails of `stdout` and `stderr` (read both: many test runners report on stderr).
- `prized prompt ls --json` lists prompt runs; `prized events --json` shows the newest run's events, and `prized events --follow` follows it live. These two do not wake a paused box.
- `prized status --json`: the box, its sync and ports from this machine's view.

## 7. Pause and resume

- `prized box pause <box> --json`: compute stops, the disk stays, billing drops to the asleep rate. It returns at once; `prized box ls --json` shows `observedState` `suspended` once it has finished. Nano through Small keep their running processes through a pause; Medium and up restart them.
- `prized box resume <box> --wait --json` wakes it. `prized ssh`, `prized exec` and `prized prompt` also wake a paused box.
- Auto-pause: a box pauses itself after sitting idle for its window. Set it with `prized box auto-pause <box> 2h` (30m to 7d) or `off`. On the free credit the window defaults to 2 hours and is capped at 12 hours, and neither pauses a box in its first 24 hours; a window you set applies from the start. On a plan or after a top-up it runs as set. Agent output, a `prized prompt` run and a `--keep-awake` job count as use, with two limits: on the free credit, a coding agent's own screen stops counting after 4 hours as the only sign of use, and a `prized prompt` run that prints nothing for 6 hours stops counting. A pause deadline, quiet hours or an empty balance still pause a box.

## 8. What it costs

Read https://prized.dev/pricing.md and quote from it: each size's rate awake and asleep, and the plan that runs it around the clock. A run's cost is its hours awake times the awake rate, plus its hours paused times the asleep rate. Prized bills only the box; Claude Code itself runs on the user's own Claude plan or API key, as on their laptop. The balance and plans are at https://prized.dev/dashboard/billing. A refusal for money (`CONFLICT` or `CHECK_FAILED` with a billing hint) says what lifts it: tell the user, and never pick a plan or pay for them.

## 9. Delete, only when asked

`prized box delete <box> -y --json` deletes the machine and its disk. For 7 days its last state can usually be restored, but not for a box deleted within an hour of being created or under zero data retention. Confirm the box's name with the user first.
