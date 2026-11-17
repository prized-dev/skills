# Prized plugin for coding agents

Give your coding agent a cloud dev box. With the Prized plugin, Claude Code copies your project to a [Prized](https://prized.dev) box, a Linux machine that stays on, and keeps working there with your laptop closed. It can also create, check on, pause and resume the box, tell you what it costs, and run code in Prized Sandboxes.

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
- `.github/`: the hourly sync of the sandbox skill from prized.dev, and the checks. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE)
