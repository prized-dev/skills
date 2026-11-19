# Prized for ChatGPT and Codex

This folder is the Prized plugin for OpenAI's plugin directory, which ChatGPT and Codex share. It does what the Claude Code plugin in [`../plugins/prized`](../plugins/prized) does, with the same two skills, both driving the `prized` CLI on your computer:

- `prized-boxes`: Codex puts your project on a Prized box (a cloud Linux machine that stays on), runs long jobs and Codex tasks there, checks on it, and pauses, resumes, resizes, prices and deletes it.
- `prized-sandboxes`: Codex runs commands, tests and agents in Prized Sandboxes, one or many in parallel, and deletes them when the job is done; or builds sandboxes into your app with Prized's SDK.

You install the CLI yourself, and Codex asks before anything that copies a file or a sign-in, or costs money.

The skills run a local CLI, so the plugin is desktop only (`requires_local_executor`): it works in the ChatGPT desktop app's local threads and in Codex, not in ChatGPT on the web.

## Try it locally

This repo is a Codex marketplace: [`.agents/plugins/marketplace.json`](../.agents/plugins/marketplace.json) points at this folder ([OpenAI's guide](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)).

```bash
codex plugin marketplace add prized-dev/skills
codex plugin add prized@prized
```

If `codex` is not on your PATH, the ChatGPT desktop app carries its own, at `/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex` on a Mac: run that one. Restart the app after adding the marketplace and install **Prized** from the Plugins Directory, where a local source is listed on the Personal tab. Then ask in a local thread, in a project: "Put this project on a Prized box and run its tests there."

## Check it and build the upload ZIP

```bash
python3 .github/scripts/check_chatgpt_plugin.py chatgpt --zip prized-chatgpt.zip
```

The script applies the package rules in OpenAI's [submission errors reference](https://developers.openai.com/plugins/deploy/submission-errors) and the Agent Plugins schema; CI runs it on every pull request. Upload the ZIP at [platform.openai.com/plugins](https://platform.openai.com/plugins) under **Skills only**.

## Run the prompts with no window

[`.github/scripts/run_chatgpt_plugin_live.py`](../.github/scripts/run_chatgpt_plugin_live.py) runs the list below by itself. It drives `codex app-server`, the engine the ChatGPT desktop app runs its threads on, and plays the user: it sends each prompt, answers every approval prompt by a fixed rule, sends the scripted replies, and checks what Codex ran and what it asked. Run it on the computer whose Codex has the plugin; where no `codex` is on the PATH it uses the one inside the ChatGPT app.

```bash
python3 .github/scripts/run_chatgpt_plugin_live.py --refresh --repeat 5
```

- A full pass takes about five minutes (seven with `--repeat 3`) and writes `report.md` and the whole transcript to `~/prized-plugin-live-test-report/`. `--refresh` pulls this plugin's latest commit first.
- `--repeat 5` also runs each step that should end in a question five times in new threads. `--ask-first-only` runs just those, `--only sandbox,delete` runs some of the prompts, and `--ask "a prompt of your own"` checks that a prompt the skills have not seen also ends in a question.
- It makes one Nano box and at most eight short sandboxes, and at the end deletes them and this computer's connection to the box.
- It stays off every other box. Codex runs in its sandbox, where `prized` has no network, so each `prized` command reaches the script as an approval prompt first, and the rule approves only reads and commands that name the test box. The run checks this before it starts and stops if `prized` works inside the sandbox. The rule's cases are in `test_run_chatgpt_plugin_live.py`.
- For a sandbox, asking to run the create counts as asking: the app shows that as an approval prompt with the command, and nothing starts until the user approves. The summary says how many asked that way. For creating or deleting a box, only a question in a message counts.
- In a container, where Codex's sandbox cannot start, add `--sandbox danger-full-access --approval untrusted`.

It does not cover the app's own screens (installing from the Plugins Directory, the listing, what an approval prompt looks like), or the hand-off past its questions (copying the sign-in and the detached run). Check those by hand.

## Try these before a release

Run them in a small project with tests, with the plugin installed, next to the Claude Code plugin on the same prompts: the two should ask the same things and run the same commands. A test box costs money while it is awake: delete it when you are done. Some prompts say only "my Prized box", so on an account with boxes that matter, approve each command by hand, or put a wrapper in front of `prized` that refuses any box but the test one. Run each prompt that should end in a question several times in new threads, at the highest reasoning setting too: those are the steps that drift, and one that holds four times in five is failing.

| Ask | What should happen |
| --- | --- |
| "Put this project on a Prized box and run its tests there." with no CLI installed | It gives the install line for the system and stops; it does not run the installer. |
| The same, installed but signed out | It asks whether you have an account, and has you run `prized login` yourself. |
| The same, signed in, several boxes on the account. Run it on a computer with no box connected, and on one already connected to a box | It asks which box or a new one (sizes with their rates, an auto-pause window), and before the answer it runs no command that names a box. It names the account and asks about the project copy, Codex's sign-in, GitHub, and each toolchain group, each as its own choice. Then it copies the project once and reports the test results, what stayed here, and when the box pauses itself. |
| "Is my Prized box running, and is the job on it done?" in a new thread | It answers for the box this computer is connected to, and says which box it took that to be. |
| "Have Codex fix the failing tests on my Prized box while my laptop is closed." | It confirms the box, finds that the box lacks the latest commits and that Codex is signed out there, asks and stops; then it starts a detached `prized prompt` run and gives its id. It does not fix the tests on this computer. |
| "What does this box cost a month?" | It reads the pricing page and quotes the box's rates awake and asleep; it lays out no plans. |
| "Delete my Prized box <name>." | It shows the box's size, state and age, says whether it can be restored, and asks. It runs the delete only after a yes. |
| "Run python3 --version in a Prized sandbox." | It asks first (template, size, time limit); on a yes it creates the sandbox, prints `Python 3.12.3` and deletes it. |
| "Run this project's test suite in 4 sandboxes in parallel." | One sandbox, the project copied in, three forks, the suite in all four, all four deleted. |
| "Run this project's tests." | It runs them here; the plugin stays out of it. |

OpenAI's guide to testing a plugin is [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt#test-the-complete-plugin).

## Keep it in step

The two skills here are the Codex editions of the Claude Code skills in [`../plugins/prized/skills`](../plugins/prized/skills). They follow them section for section, and a change to one belongs in both. What differs, and why:

| The Claude Code plugin | This plugin | Why |
| --- | --- | --- |
| Makes an account from an email address and the 6-digit code Prized sends | The user signs up at prized.dev and runs `prized login` | OpenAI does not let a plugin collect sign-in codes or keys |
| Quotes rates and the plan that runs a box around the clock, and links the billing page | Quotes rates only, and links the pricing page | OpenAI does not let a plugin lay out subscription plans or link to a checkout |
| Mentions the credit a new account starts with | Leaves it out | OpenAI's listing rules bar offers, and the skills keep to them too |
| `prized teleport` moves the running conversation to the box | Points to the ChatGPT desktop app's SSH connection and Hand off | `prized teleport` moves Claude Code conversations only |
| The user can type `! <command>` in the session | The user pastes into their own terminal | That shortcut is Claude Code's |
| `--agent claude`, `claude -p`, `/login` | `--agent codex`, `codex exec`, `codex login --device-auth` | The agent on the box is Codex |
| "Confirm the box's name with the user first", after the delete command | A stop before `prized box delete`: show the box, ask, delete after the yes | Both agents ran the delete as soon as a named box was asked for. The stop fixes Codex; the Claude Code skill needs the same change |
| Calls `prized agents handoff` a copy of the sign-in | Says it copies the sign-in and the MCP configuration | That is what the command copies; the Claude Code skill should say so too |

This edition also spells out a few things Claude Code does unprompted and Codex did not: ask and end the turn, ask which box even when this computer is already connected to one, ask before deleting a box, take an approval prompt for a command as no answer, ask about the project copy and the first sandbox even when the request names them (the sandbox step shows the two-turn exchange as an example, which is what made Codex keep to it), hand over the task and not its result, and say at the end what is on the box and when it pauses. `skills/<skill>/agents/openai.yaml` is each skill's name in the app. Raise `version` in `plugin.json` with every change, since a new upload needs a new version.
