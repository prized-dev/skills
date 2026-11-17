# Contributing

Issues and pull requests are welcome.

## The skills

The plugin is in `plugins/prized/`. `plugins/prized/skills/prized-boxes` is maintained in this repo: pull requests are welcome.

`plugins/prized/skills/prized-sandboxes` is a mirror of the skill prized.dev publishes, updated every hour by the Sync skill workflow, so a pull request that edits it would be overwritten. The mirror leaves out the skill's scripts: Claude's plugin directory takes only Markdown, text, JSON, YAML and images from an organization it hasn't verified, so keep `plugins/prized/` to those (a test checks it). For a fix or a request to it, open an issue or email team@prized.dev.

## The plugin and the workflows

Pull requests are welcome for the plugin manifests (`plugins/prized/.claude-plugin/`, `plugins/prized/.cursor-plugin/`, `plugins/prized/plugin.json`), the marketplace (`.claude-plugin/marketplace.json`), the READMEs and `.github/`. Before you open one:

```sh
python3 -m unittest discover -s .github/scripts
npx -y @anthropic-ai/claude-code@2.1.310 plugin validate --strict .
npx -y @anthropic-ai/claude-code@2.1.310 plugin validate --strict plugins/prized
```

CI runs the same checks. Never commit a key, a `.env` file or a token.

## Security

Report a vulnerability to team@prized.dev rather than in a public issue.
