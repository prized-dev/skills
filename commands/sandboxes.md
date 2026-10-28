---
description: List the Prized sandboxes in your workspace with what each costs, and clean up the ones these commands left behind ("clean").
argument-hint: "[clean]"
disable-model-invocation: true
---

Show what is running in the user's Prized workspace and what it costs. $ARGUMENTS

Use `list_sandboxes` from this plugin's `sandboxes` MCP server (if it is not available, tell the user to check `/mcp` and stop), then show one table: id, state, template, shape, labels, and when it is deleted at the latest. Add what each costs from https://prized.dev/pricing: a running sandbox bills \$0.04 per vCPU-hour, \$0.0125 per GB of memory an hour and \$0.0001 per GB of disk an hour (4 vCPU, 8 GB and 10 GB is \$0.261 an hour), billed by the second. A paused one bills only storage (its disk plus its saved memory), and the workspace's first 20 GB of paused storage are free, then \$0.05 per GB a month. End with the total an hour for what is running now, and the paused storage.

Mark the sandboxes this plugin made: those with a `prized-plugin` label (from `/prized:offload` and `/prized:fork`) or `created-by=prized-sandbox-mcp` (made by the sandbox tools).

If the text above is `clean`, find what these commands left behind:

- **Finished offload jobs:** sandboxes labelled `"prized-plugin": "offload"` where `run_command` `cat ~/job/exit` shows an exit code. List the files each job wrote with `find "$(cat ~/job/dir)" -newer ~/job/dir -type f | head -20`. Keep any whose job is still running.
- **Leftover fork sandboxes:** sandboxes labelled `"prized-plugin": "fork"` that are paused. A fork in progress is running; one left behind pauses after 15 idle minutes.

Show that list, with the files each finished job wrote, and ask the user to confirm (and whether to `download` anything first). Then delete what they confirm, and list again to show what is left. Never delete a sandbox without a `prized-plugin` label: name it and tell the user to delete it themselves if they mean to.

If a tool answers that the Prized API key is missing or refused, tell the user to run `/plugin`, open Prized on the Installed tab, choose Configure options and paste a key from https://prized.dev/dashboard/workspace/api-keys (or export `PRIZED_API_KEY` and restart Claude Code), and stop.
