# Prized for ChatGPT and Codex

This folder is the Prized plugin for OpenAI's plugin directory, which ChatGPT and Codex share. It has one skill, `prized-boxes`: Codex puts your project on a Prized box (a cloud Linux machine that stays on), runs long jobs and Codex tasks there, and checks on, pauses, resumes and resizes the box, all through the `prized` CLI on your computer. You install the CLI yourself, and Codex asks before anything that copies a file or a sign-in, or costs money.

The skill runs a local CLI, so the plugin is desktop only (`requires_local_executor`): it works in the ChatGPT desktop app's local threads and in Codex, not in ChatGPT on the web.

## Try it locally

This repo is a Codex marketplace: [`.agents/plugins/marketplace.json`](../.agents/plugins/marketplace.json) points at this folder ([OpenAI's guide](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)).

```bash
codex plugin marketplace add prized-dev/skills
codex plugin add prized@prized
```

In the ChatGPT desktop app, restart it after adding the marketplace and install **Prized** from the Plugins Directory. Then ask in a local thread, in a project: "Put this project on a Prized box and run its tests there."

## Check it and build the upload ZIP

```bash
python3 .github/scripts/check_chatgpt_plugin.py chatgpt --zip prized-chatgpt.zip
```

The script applies the package rules in OpenAI's [submission errors reference](https://developers.openai.com/plugins/deploy/submission-errors) and the Agent Plugins schema; CI runs it on every pull request. Upload the ZIP at [platform.openai.com/plugins](https://platform.openai.com/plugins) under **Skills only**.

## Try these before a release

Run them in a small project with tests, with the plugin installed, and compare with the last release. A test box costs money while it is awake: delete it when you are done.

| Ask | What should happen |
| --- | --- |
| "Put this project on a Prized box and run its tests there." with no CLI installed | It gives the install line for the system and stops; it does not run the installer. |
| The same, installed but signed out | It asks you to run `prized login` yourself. |
| The same, signed in, no box connected to this computer | It names the account, asks which box or a new one (size and auto-pause window), then copies the project once and reports the test results, what stayed here, and when the box pauses itself. |
| "Is my Prized box running, and is the job on it done?" in a new thread | It answers for the box this computer is connected to, without asking which. |
| "Have Codex fix the failing tests on my Prized box while my laptop is closed." | It checks that the box has the latest commits and that Codex is signed in there, asks about what is missing and stops; then it starts a detached `prized prompt` run and gives its id. It does not fix the tests on this computer. |
| "Bring that fix back to this laptop, then pause the box." | The fix lands here, and the box shows as paused. |
| "Run this project's tests." | It runs them here; the plugin stays out of it. |

OpenAI's guide to testing a plugin is [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt#test-the-complete-plugin).

## Keep it in step

`skills/prized-boxes/SKILL.md` here is the Codex edition of [`../plugins/prized/skills/prized-boxes`](../plugins/prized/skills/prized-boxes/SKILL.md), the Claude Code skill. A change to one usually belongs in both. This edition differs on purpose: it names Codex, not Claude Code; the user signs up and runs `prized login` themselves (the skill never asks for a sign-in code); it quotes no prices and links the [pricing page](https://prized.dev/pricing) instead; and it covers resizing a box and the ChatGPT app's SSH connection. It also takes the box this computer is connected to as the user's box, asks only the copy questions a request needs, and checks the box's code and Codex's sign-in there before a hand-off. `skills/prized-boxes/agents/openai.yaml` is the skill's name in the app. Raise `version` in `plugin.json` with every change, since a new upload needs a new version.
