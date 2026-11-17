# Contributing

Issues and pull requests are welcome.

## The plugin

The plugin is `plugins/prized/`: its manifests (`.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, the portable `plugin.json`), its two skills, icon, README and license. `.claude-plugin/marketplace.json` at the root lists it. Pull requests are welcome for all of it and for `.github/`.

Both skills are maintained here, written for Claude Code and the `prized` CLI. Keep them short and send Claude to Prized's docs for what changes (prices, limits, API routes). Claude's plugin directory holds or blocks a plugin for a few patterns, and the checks below keep them out:

- Only Markdown, text, JSON, YAML and images in `plugins/prized/`: no scripts, and nothing starting with `#!`.
- No download piped into a shell in a skill: Claude gives the user the CLI's install line to run themselves.
- No API key read from the user's environment, in a skill or the README: the CLI keeps the key.

Raise `version` in all three manifests with every change to the plugin, or installed copies won't update. Before you open a pull request:

```sh
python3 -m unittest discover -s .github/scripts
npx -y @anthropic-ai/claude-code@2.1.310 plugin validate --strict .
npx -y @anthropic-ai/claude-code@2.1.310 plugin validate --strict plugins/prized
```

CI runs the same checks. Never commit a key, a `.env` file or a token.

## The ChatGPT and Codex plugin

`chatgpt/` is a separate plugin for OpenAI's plugin directory, with its own `plugin.json` and a Codex edition of the boxes skill; `.agents/plugins/marketplace.json` lists it for Codex. It lives outside `plugins/prized`, so a change to it never changes the Claude plugin or its version. Raise `version` in `chatgpt/plugin.json` with every change to it. The same rules apply (text and images only, no piped installers, no keys from the environment), plus OpenAI's (no prices or offers) and ours (the skill names Codex, never Claude). Check it, and build the ZIP to upload at platform.openai.com/plugins:

```sh
python3 .github/scripts/check_chatgpt_plugin.py chatgpt --zip prized-chatgpt.zip
```

## Security

Report a vulnerability to team@prized.dev rather than in a public issue.
