---
name: prized-boxes
description: Put the user's project on a Prized box, a cloud Linux dev machine where Codex and long jobs keep running with the laptop closed, using the prized CLI in a local shell. Use when the user wants a coding agent to keep working overnight or after they close the laptop, wants a cloud dev box or a remote machine for their agents, asks to move this project or this conversation to the cloud, wants a long build, test run or eval to run somewhere else, or asks to check on, pause, resume, resize or price a Prized box.
---

# Prized boxes

A box is a cloud Linux machine of the user's own from Prized (https://prized.dev): sudo, its own disk, no maximum run time. Codex runs on it in a tmux session that keeps going when the laptop sleeps, and the user looks in from a terminal, a browser or the ChatGPT app. A box bills by the hour while awake and only for its disk while paused. The docs are the source of truth: https://prized.dev/llms.txt lists every page, and adding `.md` to a docs URL gives its Markdown.

This skill runs the `prized` CLI in a shell on the user's own computer. If you have no such shell in this conversation, run nothing and do not claim you did: say the steps need a local thread (the ChatGPT desktop app or Codex), and give the user the commands below to run themselves.

## Rules

The user's explicit instructions come before the defaults here. These hold either way:

- Ask the user before you create, resize or wake a box (all cost money), copy the project, or copy any credential. Pass only the flags they said yes to.
- When you need an answer, ask and end your turn there. Don't start the task on this computer while you wait, unless they asked you to. A prompt to approve a command is not that answer: it shows the command, not what it will do to their box, so where a step says to ask first, ask in a message and run the command only after their reply.
- Copy, never move or delete their files. The project goes to the box once, one way (`--copy-once`). Start a sync only if they ask for one.
- Never ask the user for a password, an API key or a sign-in code, and never make an account for them. Never run `prized login` yourself, and never switch the account this computer uses.
- Never print, log or commit a key, never put one on a command line, and never read `~/.config/prized`.
- Act only on the box the user named. Never pause, resize or delete a box they did not ask about.
- Quote prices only from https://prized.dev/pricing.md, read at the time, never from memory. Quote rates, not plans: for plans, link https://prized.dev/pricing. Never start a checkout, pass along a billing or checkout link, or pay for them: if a command is refused for money, say what the refusal says is needed.
- Add `--json` to `prized` commands: each prints one JSON object with an `ok` field, and failures carry `error.code` and a `hint` to relay (codes: https://prized.dev/docs/cli.md#for-agents-and-scripts).
- Every `prized` command needs the network, and setup writes outside this folder. If your sandbox blocks a command, ask the user to approve running it outside the sandbox; do not read a network error as a sign-in problem. `prized box new --wait` and `prized setup` can take several minutes: give them a 10 minute timeout.
- When a step is the user's to do, give the reason itself in plain words (`prized login` confirms in their browser, so it has to be them).

## The key, and where it goes

The CLI signs in with a Prized API key. `prized login` (the user, in a browser) saves it under `~/.config/prized`, and the CLI sends it only to Prized's API at `api.prized.dev`. You never handle the key yourself. A key made for Sandboxes only cannot create boxes: boxes need Full access or Boxes: Write. If a box command is refused for that reason, tell the user; `prized login` makes a key that can.

## 1. Install the CLI

If `prized version` fails, ask the user to install the CLI themselves. Read https://prized.dev/docs/quickstart.md#2-install-the-cli and give them the exact install line for their system, ready to paste into their own terminal. Don't run the installer yourself: it downloads a program and runs it on their computer, so starting it is theirs to do. The installer adds the CLI to PATH for new terminals, not for this shell: if `prized` is still not found, write it as the full path the installer printed (usually `~/.local/bin/prized`) in every command after. If a command or flag below is unknown, ask, then run `prized update`.

## 2. Sign in

Run `prized box ls --json`. If it works, this computer is signed in: keep that account. If it fails with `AUTH`, ask whether the user has a Prized account.

- They do: ask them to run `prized login` in their own terminal (it opens the dashboard in their browser to make a key for this computer) and to tell you when it has finished.
- They don't: they sign up at https://prized.dev/sign-in, then run `prized login` in their own terminal.

Then run `prized box ls --json` again. If it fails with any other code, tell the user what it says.

## 3. A box

`prized box ls --json` lists their boxes with `hostname`, `observedState`, `tier` (its size) and `autoPauseMin`; on a team's account that includes teammates' boxes. If there is none, or they want a new one, ask in one message which size (with its rate from the pricing page) and how long it may sit idle before it pauses itself, then run `prized box new <name> --size <size> --auto-pause <window> --wait --json`. Offer an auto-pause window (30m to 7d, 2h is a good default): without it, a box can start with auto-pause off and bill by the hour until someone pauses it. Without `--size`, Prized picks a size the balance runs comfortably. Sizes, smallest first: Nano (`nano`), Micro (`micro`), Extra Small (`lite`), Small (`flow`), Medium (`pro`), Large (`max`), Extra Large (`ultra`); `prized box new --help` lists the GPU sizes. If the account cannot run a size, the CLI refuses with a hint: relay it.

With more than one box on the account, do not pick one, and do not run a command that names a box yet (no `--box <name>`, no box as an argument, not even with `--dry-run`). Which box is the user's to say, even when this computer is already connected to one, and even when the request only says "a box". First send one message and stop: the boxes that could be theirs, which of them this computer is connected to (`prized status --json` names it as `box.name`), and the offer of a new one, with the sizes, each one's rate from the pricing page, and an auto-pause window to pick. Section 4's questions can go in the same message. After their answer, name the box in every command: as the argument where a command below shows `<box>`, and as `--box <name>` everywhere else (`prized exec --box <name> --cwd ... -- ...`, `prized setup`, `prized status`).

One case needs no question: to only check on a box (its state, its jobs), use the box this computer is connected to, and say which box you took it to be. If `prized status --json` fails with `no config`, no box is connected here yet: `prized setup --box <name>` connects one (section 4), and until then `prized exec`, `prized prompt` and `prized agents` have no box to reach.

## 4. Move the project onto it

Add `--no-advisor` to every `prized setup` and `prized env` command: otherwise setup sends the project's manifests (README, Makefile, package.json and the like, secrets redacted) to Prized's advisor to tailor its questions.

1. Run `prized setup --dry-run --json --non-interactive --no-advisor --copy-once .` in the project. It changes nothing, and its `login` step names the account. (`prized version` saying the daemon is not running is fine: setup starts it.) If it refuses this folder (exit 2), use `--no-project` in place of `--copy-once .`.
2. Ask in one message: may you copy this project to the box once, with no sync (name the account and the box)? Ask that even when the request was to put the project on a box, since they have not seen which account and box it goes to. Copy Codex's sign-in, MCP servers and settings there (`--agent codex`; an API-key sign-in is copied as is, while a ChatGPT sign-in never travels, so the box needs its own sign-in afterwards, step 4)? Their GitHub CLI token and git identity (`--gh`)? For their toolchain, run `prized env plan --json --no-advisor` and read them the groups; the ones they pick go in `--env <groups>`. Its output is long: the groups are `plan.groups[]`, each with `group` (the name for `--env`) and `question`. Put each of these to them as its own choice, even when the task is only to run tests: don't answer any of them for the user. Say that Codex's sign-in on the box is what lets Codex keep working there with their laptop closed. Never copy a home folder, the Desktop or a folder inside `~/Prized`.
3. Run setup once, with a flag for every answer: `--agent codex` or `--no-agents`, `--gh` or `--no-gh`, `--env <groups>` or `--no-env`. For example, a yes to the copy and no to the rest is `prized setup --json --non-interactive --no-advisor --copy-once . --no-agents --no-gh --no-env`. It copies the project to `~/code/<folder>` on the box (`.git` included; `node_modules`, virtualenvs, build caches and `.env` files stay here). Secrets go only with `--env-secrets`, its own yes: it copies the project's `.env` files, CLI sign-in files such as `~/.aws`, `~/.config/gcloud` and `~/.kube/config`, and secret-looking variables from their shell files, so name all three when you ask. Before running the project's tests there, install its dependencies on the box: `--env node` or `--env python` does it from a lockfile, or run the install with `prized exec`.
4. Read `steps[]` in the JSON: each step has a `status` of `done`, `skipped` or `failed` and a `detail`. The `project` step's detail names the folder on the box; a `failed` one carries a hint to relay. If the agents step reports codex as `manual`, Codex is not signed in on the box: the user runs `prized agents handoff codex` in their own terminal (it opens the sign-in page in their browser), or `prized ssh`, then `codex login --device-auth` on the box, once (device-code sign-in has to be turned on in their ChatGPT security settings).

Setup never overwrites a folder on the box that holds files. If `~/code/<folder>` is already there, the `project` step comes back `skipped` and the box keeps the copy it had: stop and say so, compare the two (`git log` and `git status` here and on the box), and ask how to bring the box up to date before you run anything on the older copy. Changes get there with git (commit and push here, pull there), or with `prized cp` for a patch or a few files. Nothing comes back by itself either: work done on the box stays in `~/code/<folder>` there until the user pushes it from the box or copies it down. To have the two folders follow each other instead, the user starts a sync (https://prized.dev/docs/sync.md).

Already deep in a conversation they want to keep? No `prized` command moves a Codex conversation to the box. In the ChatGPT desktop app on a Mac, the user opens Settings > Connections, clicks Add under SSH connections from this Mac, and ticks the box; from then on they can start chats on the box (projects are in `~/code`), and the app's Hand off moves a chat and its git state there and back. If setup skipped Codex's sign-in, `prized setup --agent chatgpt` signs Codex in there, on the user's yes. Those chats are driven from the Mac and stop when it sleeps: for work that goes on with the laptop closed, use section 5. Guide: https://prized.dev/docs/codex.md

## 5. Run Codex or a long job there

| What | Command |
| --- | --- |
| Run one command in the project | `prized exec --cwd code/<folder> -- npm test` |
| A long job that outlives this session | `prized exec --detach --keep-awake --cwd code/<folder> -- ./long-job.sh` (returns a `processId`; auto-pause waits for the job to exit) |
| Hand Codex a task and walk away | `prized prompt --provider codex --cwd code/<folder> --detach "<the task>"` (headless `codex exec` on the box; `--auto` turns off approvals and the sandbox, so add it only on the user's yes) |
| Codex in a session they open themselves | give them `prized agents run codex --attach --dir code/<folder>`; they reattach later with `prized ssh -s codex` |

When the user asks for work to go on while they're away, overnight or with the laptop closed, it has to run on the box: a `prized prompt` run, a session they open, or a detached job. Doing the work from this session with `prized exec` stops when this session does, so don't do that and call it handed off. Don't do the task here first and send the result over either: hand over the task. Codex on the box starts with none of this conversation, so write the `prized prompt` text to stand alone (what to do, in which files, how to check it), and it works on the box's copy of the project: check that copy has the commits the user means (section 4) before you start it.

If Codex isn't signed in on the box (`prized agents ls --json` shows `box.signed_in` under `codex`, and `prized prompt` refuses with `CHECK_FAILED`), ask which they want: you copy this computer's Codex sign-in and MCP configuration (`prized agents handoff codex --box <box>` copies both: an API-key sign-in is copied as is, and for a ChatGPT sign-in the command reports `manual` with the steps left for them), or they sign in themselves (`prized agents handoff codex` in their own terminal, which opens the sign-in page in their browser, or `prized ssh <box>`, then `codex login --device-auth`, once).

`--detach` runs return at once, and closing the laptop leaves them running. `prized exec` runs what follows `--` under `sh -c` in the box's home folder, so pass a shell line as one quoted string. `prized prompt` needs Codex signed in on the box; without `--auto` it runs in Codex's `workspace-write` sandbox, which edits and runs commands in the project with no network. If `--keep-awake` is refused (an older box agent), ask, then run `prized box auto-pause <box> off` and start the job without it.

## 6. Check on it

- `prized box ls --json`: every box, with `hostname`, `observedState` (`running`, `suspending`, `suspended`, `deep_sleep` for a box paused over 3 days, which wakes in a minute or two with its processes restarted), `tier` (its size) and `autoPauseMin`. `prized box info <box> --json` adds its last events.
- `prized exec --ps --json` lists detached jobs; `prized exec --status <processId> --json` shows one's `running`, `exitCode`, and the tails of `stdout` and `stderr` (read both: many test runners report on stderr).
- `prized prompt ls --json` lists prompt runs; `prized events --json` shows the newest run's events, and `prized events --follow` follows it live. These two do not wake a paused box.
- `prized status --json`: the box, its sync and ports from this computer's view.

## 7. Pause, resume and resize

- `prized box pause <box> --json`: compute stops, the disk stays, billing drops to the asleep rate. It returns at once; `prized box ls --json` shows `observedState` `suspended` once it has finished. Nano through Small keep their running processes through a pause; Medium and up restart them.
- `prized box resume <box> --wait --json` wakes it, and billing at the awake rate starts again. `prized ssh`, `prized exec` and `prized prompt` also wake a paused box, so tell the user and ask before running them on one.
- Auto-pause: a box pauses itself after sitting idle for its window. Set it with `prized box auto-pause <box> 2h` (30m to 7d) or `off`. On an account with no plan and nothing paid in, the window defaults to 2 hours and `off` or anything over 12 hours runs as 12 hours, and neither the default nor that cap pauses a box in its first 24 hours; a window you set applies from the start, first day included. On a plan or after a top-up it runs as set. Codex printing in its session, a `prized prompt` run and a `--keep-awake` job count as use, with two limits: on an account with no plan, a coding agent's own screen stops counting after 4 hours as the only sign of use, and a `prized prompt` run that prints nothing for 6 hours stops counting. A pause deadline, quiet hours or an empty balance still pause a box.
- Resize, only on the user's yes, since it changes what the box costs: `prized box resize <box> <size> --json`. The box restarts at the new size with its files intact, so running processes stop. Disks grow with a bigger size and never shrink. A refusal exits 5 with a hint: relay it.

## 8. What it costs

Read https://prized.dev/pricing.md and quote from it: each size's rate awake and asleep. A run's cost is its hours awake times the awake rate, plus its hours paused times the asleep rate. Prized bills only the box; Codex itself runs on the user's own ChatGPT plan or OpenAI API key, as on their laptop. For plans, link https://prized.dev/pricing: don't lay them out or pick one. A refusal for money (`CONFLICT` or `CHECK_FAILED` with a billing hint) says what lifts it: tell the user, and never pick a plan or pay for them.

## 9. Delete, only when asked

Do not run `prized box delete` yet. First run `prized box info <box> --json`, then send the user one message and stop: "Delete `<box>`? <its size, its state, when it was made>. The machine and its disk go, and <whether it can be restored>." Their request to delete it is not an answer to that, and neither is an approval prompt for the command: they have not seen which box that name is on this account, or whether it can come back. In the turn that asks, do not run or request `prized box delete`.

After their yes, `prized box delete <box> -y --json` deletes the machine and its disk. For 7 days its last state can usually be restored, but not for a box deleted within an hour of being created or under zero data retention.

## When you finish

Tell the user what is on the box and where (`~/code/<folder>`), what you copied and what stayed here, and what is still running there: a job's or a run's id and the command that checks it. Say whether the box is awake and when it pauses itself, since it bills by the hour until then.
