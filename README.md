# Prized skills

The Prized plugin gives Claude Code its own Linux computers: [Prized Sandboxes](https://prized.dev/docs/sandboxes), microVMs it creates, runs commands in, forks and deletes. It brings the Prized Sandboxes MCP server and the `prized-sandboxes` skill. The same repo is a plugin marketplace for Codex and a skill for Cursor and other agents.

## Install in Claude Code

You need Node.js 20 or later.

```text
/plugin marketplace add prized-dev/skills
/plugin install prized@prized
```

Start a new session and ask Claude to run `python3 --version` in a Prized sandbox.

**No Prized account?** Ask Claude to sign you up. It asks for your email, Prized emails you a 6-digit code, and you tell Claude the code. Your account comes with free credit and no card, and its key is saved for later sessions.

**Already have one?** Run `prized login`, or export `PRIZED_API_KEY` in the shell you start Claude Code from. Make a key with Sandboxes: Write on the [API keys page](https://prized.dev/dashboard/workspace/api-keys).

## Codex, Cursor and other agents

These install the skill. Export `PRIZED_API_KEY` in the shell you start your agent from; [Sandboxes onboarding](https://prized.dev/onboarding/sandboxes) signs you up with free credit and no card.

```bash
codex plugin marketplace add prized-dev/skills
codex plugin add prized@prized
```

For Cursor and other agents, the `skills` CLI asks which agents get it.

```bash
npx skills add prized-dev/skills
```

The full guide is [Use Prized from your coding agent](https://prized.dev/docs/sandboxes-coding-agents).

## What the plugin runs

- **The MCP server.** Claude Code starts [`@prized/sandbox-mcp`](https://www.npmjs.com/package/@prized/sandbox-mcp) with `npx -y @prized/sandbox-mcp@0.1.0` while a session is open; the first start downloads it from npm. Its tools create, list, fork, pause, resume and delete sandboxes, run commands, read and write files, and upload and download them. `upload` and `download` reach only the folder Claude Code runs in, and are off when that is your home folder or `/`. Sandboxes it creates pause after 15 idle minutes and carry the label `created-by=prized-sandbox-mcp`. [How it works](https://prized.dev/docs/sandboxes-mcp).
- **The skill**, instructions in [SKILL.md](skills/prized-sandboxes/SKILL.md) with three helper scripts the agent can copy into your project (Python standard library, and TypeScript with only `fetch`). It may install the `prized` CLI from `https://prized.dev/install.sh`.
- No hooks, and nothing else in the background.

The key comes from `PRIZED_API_KEY`, else the `prized` CLI's login (where sign-up saves it, `~/.config/prized/cp.token`, readable only by you). It is sent only to Prized, at `api.prized.dev` and each sandbox's own address, and no tool shows it. Each sandbox bills your Prized workspace per second while it runs; prices are on the [pricing page](https://prized.dev/pricing).

## Where the skill comes from

The skill is maintained with the Prized product and published at [prized.dev/SKILL.md](https://prized.dev/SKILL.md). A GitHub Action copies the published version into `skills/` every hour and checks it against the digest prized.dev lists, so this repo installs the same files as `npx skills add https://prized.dev`. Edits to `skills/` here are overwritten. For a fix or a request, open an issue or email team@prized.dev.

## License

[Apache-2.0](LICENSE)
