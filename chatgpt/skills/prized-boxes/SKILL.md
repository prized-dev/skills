---
name: prized-boxes
description: Put the user's project on a Prized box, a cloud Linux dev machine where Codex and long jobs keep running with the laptop closed, using the prized CLI in a local shell. Use when the user wants a coding agent to keep working overnight or after they close the laptop, wants a cloud dev box or a remote machine for their agents, wants a long build, test run or eval to run somewhere else, or asks to check on, pause, resume or resize a Prized box.
---

# Prized boxes

A box is a cloud Linux machine of the user's own from Prized (https://prized.dev): sudo, its own disk, no maximum run time. Codex runs on it in a tmux session that keeps going when the laptop sleeps, and the user looks in from a terminal, a browser or the ChatGPT app. A box bills by the hour while awake and only for its disk while paused. The docs are the source of truth: https://prized.dev/llms.txt lists every page, and adding `.md` to a docs URL gives its Markdown.

This skill runs the `prized` CLI in a shell on the user's own computer. If you have no such shell in this conversation, run nothing and do not claim you did: say the steps need a local thread (the ChatGPT desktop app or Codex), and give the user the commands below to run themselves.

## Rules

The user's explicit instructions come before the defaults here. These hold either way:

- Ask the user before you create, resize or wake a box (all cost money), copy the project, or copy any credential. Pass only the flags they said yes to.
- When you need an answer, ask and end your turn there. Don't start the task on this computer while you wait, unless they asked you to.
- Copy, never move or delete their files. The project goes to the box once, one way (`--copy-once`). Start a sync only if they ask for one.
- Never ask the user for a password, an API key or a sign-in code, and never make an account for them. Never run `prized login` yourself, and never switch the account this computer uses.
- Never print, log or commit a key, never put one on a command line, and never read `~/.config/prized`.
- Act only on the user's box (section 3). Never pause, resize or delete a box they did not ask about.
- When a step is the user's to do, give the reason itself in plain words (`prized login` confirms in their browser, so it has to be them).
- Do not quote prices or pick a plan. For rates, point the user to https://prized.dev/pricing. Never start a checkout, pass along a billing or checkout link, or pay for them: if a command is refused for money, say what the refusal says is needed.
- Add `--json` to `prized` commands: each prints one JSON object with an `ok` field, and failures carry `error.code` and a `hint` to relay (codes: https://prized.dev/docs/cli.md#for-agents-and-scripts).
- Every `prized` command needs the network, and setup writes outside this folder. If your sandbox blocks a command, ask the user to approve running it outside the sandbox; do not read a network error as a sign-in problem. `prized box new --wait` and `prized setup` can take several minutes: give them a 10 minute timeout.

## 1. Install the CLI

If `prized version` fails, ask the user to install the CLI themselves. Read https://prized.dev/docs/quickstart.md#2-install-the-cli and give them the exact install line for their system, ready to paste into their own terminal. Don't run the installer yourself: it downloads a program and runs it on their computer, so starting it is theirs to do. The installer adds the CLI to PATH for new terminals, not for this shell: if `prized` is still not found, write it as the full path the installer printed (usually `~/.local/bin/prized`) in every command after. If a command or flag below is unknown, ask, then run `prized update`.

## 2. Sign in

Run `prized box ls --json`. If it works, this computer is signed in: keep that account. If it fails with `AUTH`, ask whether the user has a Prized account.

- They do: ask them to run `prized login` in their own terminal (it opens the dashboard in their browser to make a key for this computer) and to tell you when it has finished.
- They don't: they sign up at https://prized.dev/sign-in, then run `prized login` in their own terminal.

Then run `prized box ls --json` again. If it fails with any other code, tell the user what it says.

The CLI signs in with a Prized API key: `prized login` saves it under `~/.config/prized`, and the CLI sends it only to Prized's API at `api.prized.dev`. You never handle the key yourself. Boxes need a key with Full access or Boxes: Write, so a key made for Sandboxes only cannot drive them. If box commands are refused for that reason, tell the user; `prized login` makes a key that can.

## 3. A box

`prized status --json` names the box this computer is connected to, as `box.name`. That is the user's box: use it without asking which, and say its name when you act on it.

If it fails with `no config`, or says that box is gone, no box is connected here yet. `prized box ls --json` lists the account's boxes with `hostname`, `observedState`, `tier` (its size) and `autoPauseMin`; on a team's account that includes teammates' boxes. With one box, that is theirs. With several, ask which, or whether they want a new one. `prized setup --box <name>` connects it (section 4); until then `prized exec`, `prized prompt` and `prized agents` have no box to reach.

For a new box, ask in one message which size and how long it may sit idle before it pauses itself, then run `prized box new <name> --size <size> --auto-pause <window> --wait --json`. Offer an auto-pause window (30m to 7d, 2h is a good default): without it, a box can start with auto-pause off and bill by the hour until someone pauses it. Leave out `--size` if the user has no preference, and Prized picks a size their balance runs comfortably; for rates, point them to https://prized.dev/pricing. Sizes, smallest first: Nano (`nano`), Micro (`micro`), Extra Small (`lite`), Small (`flow`), Medium (`pro`), Large (`max`), Extra Large (`ultra`); `prized box new --help` lists the GPU sizes. If the account cannot run a size, the CLI refuses with a hint: relay it.

Name any box other than `box.name` in every command: as the argument where a command below shows `<box>`, and as `--box <name>` everywhere else (`prized exec --box <name> --cwd ... -- ...`, `prized setup`, `prized status`).

## 4. Copy the project onto it

Add `--no-advisor` to every `prized setup` and `prized env` command: otherwise setup sends the project's manifests (README, Makefile, package.json and the like, secrets redacted) to Prized's advisor to tailor its questions.

1. Run `prized setup --dry-run --json --non-interactive --no-advisor --copy-once .` in the project. It changes nothing, and its `login` step names the account. If it refuses this folder (exit 2), use `--no-project` in place of `--copy-once .`.
2. Ask in one message, each as its own yes or no with your suggestion beside it, so one reply can settle them all. Ask what this request needs and leave out the rest: what you don't ask about, you don't copy.
   - The project: may you copy it to the box once, with no sync? Name the account and the box.
   - Its toolchain: run `prized env plan --json --no-advisor` and offer the groups the project uses; the ones they pick go in `--env <groups>`. Its output is long: the groups are `plan.groups[]`, each with `group` (the name for `--env`) and `question`. Tests need the project's dependencies on the box: `--env node` or `--env python` installs them from a lockfile, or run the install with `prized exec` afterwards.
   - Codex's sign-in, MCP servers and settings (`--agent codex`), when Codex itself is to work on the box: that sign-in is what lets Codex keep working there with their laptop closed. An API-key sign-in is copied as is; a ChatGPT sign-in never travels, so the box needs its own afterwards (step 4).
   - Their GitHub CLI token and git identity (`--gh`), when the work on the box has to push or open a pull request.
   - Secrets (`--env-secrets`), only when the task cannot run without them: it copies the project's `.env` files, CLI sign-in files such as `~/.aws`, `~/.config/gcloud` and `~/.kube/config`, and secret-looking variables from their shell files, so name all three when you ask.

   Never copy a home folder, the Desktop or a folder inside `~/Prized`.
3. Run setup once, with a flag for every answer and the "no" flag for what you did not ask: `--agent codex` or `--no-agents`, `--gh` or `--no-gh`, `--env <groups>` or `--no-env`. For example, a yes to the copy and no to the rest is `prized setup --json --non-interactive --no-advisor --copy-once . --no-agents --no-gh --no-env`. It copies the project to `~/code/<folder>` on the box (`.git` included; `node_modules`, virtualenvs, build caches and `.env` files stay here).
4. Read `steps[]` in the JSON: each step has a `status` of `done`, `skipped` or `failed` and a `detail`. The `project` step's detail names the folder on the box; a `failed` one carries a hint to relay. If the agents step reports codex as `manual`, Codex is not signed in on the box: the user runs `prized agents handoff codex` in their own terminal (it opens the sign-in page in their browser), or `prized ssh`, then `codex login --device-auth` on the box, once (device-code sign-in has to be turned on in their ChatGPT security settings).

Setup never overwrites a folder on the box that holds files. If `~/code/<folder>` is already there, the `project` step comes back `skipped` and the box keeps the copy it had: say so, and don't describe changes made here since as being on the box. They get there with git (commit and push here, pull there), or with `prized cp <file> :code/<folder>/<file>` for a few files. Nothing comes back by itself either: work done on the box stays in `~/code/<folder>` there until the user pushes it from the box or copies it down (`prized cp -r :code/<folder> <a new folder here>`). To have the two folders follow each other instead, the user starts a sync (https://prized.dev/docs/sync.md).

To chat with Codex on the box from the ChatGPT desktop app on a Mac, the user opens Settings > Connections, clicks Add under SSH connections from this Mac, and ticks the box; projects are in `~/code`, and if setup skipped Codex's sign-in, `prized setup --agent chatgpt` signs Codex in there, on the user's yes (https://prized.dev/docs/codex.md). Those chats are driven from the Mac and stop when it sleeps: for work that goes on with the laptop closed, use step 5.

## 5. Run Codex or a long job there

| What | Command |
| --- | --- |
| Run one command in the project | `prized exec --cwd code/<folder> -- npm test` |
| A long job that outlives this session | `prized exec --detach --keep-awake --cwd code/<folder> -- ./long-job.sh` (returns a `processId`; the box stays awake until the job exits) |
| Hand Codex a task and walk away | `prized prompt --provider codex --cwd code/<folder> --detach "<the task>"` (headless `codex exec` on the box; `--auto` turns off approvals and the sandbox, so add it only on the user's yes) |
| Codex in a session they open themselves | give them `prized agents run codex --attach --dir code/<folder>`; they reattach later with `prized ssh -s codex` |

When the user asks for work to go on while they're away, overnight or with the laptop closed, it has to run on the box: a `prized prompt` run, a session they open, or a detached job. Doing the work from this session with `prized exec` stops when this session does, so don't do that and call it handed off. Don't do the task here first and send the result over either: hand over the task.

Before you hand a task over, check two things:

- The box has the code the user means. Codex there works on the box's copy, so compare `git rev-parse HEAD` and `git status --short` here with the same on the box (`prized exec --cwd code/<folder> -- git rev-parse HEAD`). If this computer has commits or edits the box lacks, say so and ask how to bring them over (section 4) before you start Codex on the older copy.
- Codex is signed in on the box: `prized agents ls --json` shows it as `box.signed_in` under `codex`, and `prized prompt` refuses with `CHECK_FAILED` when it is not. Signing it in is the user's step: they run `prized agents handoff codex` in their own terminal, which copies an API-key sign-in as it is and opens the sign-in page in their browser for a ChatGPT one. Say the hand-off is waiting on that, and start it when they tell you it is done.

Codex on the box starts with none of this conversation: write the `prized prompt` text so it stands alone (what to do, in which files, how to check it).

`--detach` runs return at once, and closing the laptop leaves them running. `prized exec` runs what follows `--` under `sh -c` in the box's home folder, so pass a shell line as one quoted string. Without `--auto`, `prized prompt` runs in Codex's `workspace-write` sandbox, which edits and runs commands in the project with no network. If `--keep-awake` is refused (an older box agent), ask, then run `prized box auto-pause <box> off` and start the job without it.

## 6. Check on it

Check the user's box (section 3) without asking which.

- `prized box ls --json`: every box and its `observedState` (`running`, `suspending`, `suspended` and the rest). A box paused over 3 days is in deep sleep: it wakes in a minute or two with its processes restarted. `prized box info <box> --json` adds its last events.
- `prized exec --ps --json` lists detached jobs; `prized exec --status <processId> --json` shows one's state, exit code and the tails of `stdout` and `stderr` (read both: many test runners report on stderr).
- `prized prompt ls --json` lists prompt runs; `prized events --json` shows the newest run's events, and `prized events --follow` follows it live. These do not wake a paused box.
- `prized status --json`: the box, its sync and ports from this computer's view.

## 7. Pause, resume and resize

- `prized box pause <box> --json`: compute stops, the disk stays, billing drops to the asleep rate. `prized box ls --json` shows `observedState` `suspended` once it has finished. Nano through Small keep their running processes through a pause; Medium and up restart them.
- `prized box resume <box> --wait --json` wakes it, and billing at the awake rate starts again. `prized ssh`, `prized exec` and `prized prompt` also wake a paused box, so tell the user and ask before running them on one.
- Auto-pause: a box pauses itself after sitting idle for its window. Set it with `prized box auto-pause <box> 2h` (30m to 7d) or `off`. On an account with no plan and nothing paid in, the window defaults to 2 hours and `off` or anything over 12 hours runs as 12 hours, and neither the default nor that cap pauses a box in its first 24 hours; a window you set applies from the start, first day included. On a plan it runs as set. Codex printing in its session, a `prized prompt` run and a `--keep-awake` job count as use, with two limits: on an account with no plan, a coding agent's own screen stops counting after 4 hours as the only sign of use, and a `prized prompt` run that prints nothing for 6 hours stops counting. A pause deadline, quiet hours or an empty balance still pause a box.
- Resize, only on the user's yes, since it changes what the box costs: `prized box resize <box> <size> --json`. The box restarts at the new size with its files intact, so running processes stop. Disks grow with a bigger size and never shrink. A refusal exits 5 with a hint: relay it.

## 8. Delete, only when asked

`prized box delete <box> -y --json` deletes the machine and its disk. For 7 days it can usually be restored, but not a box deleted within an hour of being created or under zero data retention. Confirm the box's name with the user first.

## When you finish

Tell the user what is on the box and where (`~/code/<folder>`), what you copied and what stayed here, and what is still running there: a job's or a run's id and the command that checks it. Say whether the box is awake and when it pauses itself, since it bills by the hour until then.
