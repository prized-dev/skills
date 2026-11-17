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

## This repository

- `plugins/prized/`: the plugin, and only the plugin: its manifests, skills, icon, README and license.
- `.claude-plugin/marketplace.json`: the marketplace that lists it.
- `.github/`: the checks that run on every pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE)
