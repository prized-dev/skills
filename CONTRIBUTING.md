# Contributing

Issues and pull requests are welcome.

## The skill

`skills/` is a mirror of the skill prized.dev publishes, updated every hour by the Sync skill workflow, so a pull request that edits it would be overwritten. For a fix or a request to the skill, open an issue or email team@prized.dev.

## The plugin and the workflows

Pull requests are welcome for the plugin manifests (`.claude-plugin/`, `.cursor-plugin/`, `plugin.json`), the README and `.github/`. Before you open one:

```sh
python3 -m unittest discover -s .github/scripts
npx -y @anthropic-ai/claude-code@2.1.310 plugin validate --strict .
```

CI runs the same checks. Never commit a key, a `.env` file or a token.

## Security

Report a vulnerability to team@prized.dev rather than in a public issue.
