# Prized for ChatGPT and Codex

This folder is the Prized plugin for OpenAI's plugin directory, which ChatGPT and Codex share. It has one skill, `prized-boxes`: Codex puts your project on a Prized box (a cloud Linux machine that stays on), runs long jobs and Codex tasks there, and checks on, pauses, resumes and resizes the box, all through the `prized` CLI on your computer. It asks before anything that installs software, copies a file or a sign-in, or costs money.

The skill runs a local CLI, so the plugin is desktop only (`requires_local_executor`): it works in the ChatGPT desktop app's local threads and in Codex, not in ChatGPT on the web.

## Try it locally

Codex installs it from a local marketplace. From a folder that holds this one as `plugins/prized` and a `.agents/plugins/marketplace.json` that points at it ([OpenAI's guide](https://developers.openai.com/plugins/build/plugins#install-a-local-plugin-manually)):

```bash
codex plugin marketplace add ./my-marketplace
codex plugin add prized@<marketplace-name>
```

Then ask Codex in a project: "Put this project on a Prized box and run its tests there."

## Check it and build the upload ZIP

```bash
python3 .github/scripts/check_chatgpt_plugin.py chatgpt --zip prized-chatgpt.zip
```

The script applies the package rules in OpenAI's [submission errors reference](https://developers.openai.com/plugins/deploy/submission-errors) and the Agent Plugins schema; CI runs it on every pull request. Upload the ZIP at [platform.openai.com/plugins](https://platform.openai.com/plugins) under **Skills only**.

## Keep it in step

`skills/prized-boxes/SKILL.md` here is the Codex edition of [`../skills/prized-boxes`](../skills/prized-boxes/SKILL.md), the Claude Code skill. A change to one usually belongs in both. This edition differs on purpose: it names Codex, not Claude Code; the user signs up and runs `prized login` themselves (the skill never asks for a sign-in code); it quotes no prices and links the [pricing page](https://prized.dev/pricing) instead; and it covers resizing a box and the ChatGPT app's SSH connection. Raise `version` in `plugin.json` with every change, since a new upload needs a new version.
