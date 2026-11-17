# Prized plugin for coding agents

Give your coding agent computers in the cloud. With the Prized plugin, Claude Code puts your project on a [Prized](https://prized.dev) box, a Linux machine that stays on, and keeps working there with your laptop closed. It also runs code, tests and agents in Prized Sandboxes, microVMs that start in seconds and are deleted when the job is done.

The plugin is in [`plugins/prized`](plugins/prized): its [README](plugins/prized/README.md) says what it does, what it runs and what it sends where.

## Install

In Claude Code, add this repo as a plugin marketplace and install the plugin:

```text
/plugin marketplace add prized-dev/skills
/plugin install prized@prized
```

Or, for Claude Code, Cursor, Codex, GitHub Copilot CLI and VS Code at once:

```bash
npx plugins add prized-dev/skills
```

## ChatGPT and Codex

[`chatgpt/`](chatgpt/) is a separate plugin for OpenAI's plugin directory, which ChatGPT and Codex share: the boxes skill with Codex in place of Claude Code. It is desktop only, since it runs the `prized` CLI in a local thread. Codex and the ChatGPT desktop app install it from this repo's Codex marketplace:

```bash
codex plugin marketplace add prized-dev/skills
codex plugin add prized@prized
```

`npx plugins add prized-dev/skills` also gives Codex this edition, so Codex gets the boxes skill only, not the sandbox skill.

## This repository

- `plugins/prized/`: the plugin, and only the plugin: its manifests, skills, icon, README and license.
- `.claude-plugin/marketplace.json`: the marketplace that lists it.
- `chatgpt/`: the separate ChatGPT and Codex plugin, outside `plugins/prized` so it never changes the Claude plugin. `.agents/plugins/marketplace.json` lists it for Codex.
- `.github/`: the checks that run on every pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE)
