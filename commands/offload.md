---
description: Run a long job (a test suite, build, eval or script) in a Prized sandbox that keeps going when your laptop sleeps or you quit Claude Code. About $0.26 an hour on the default 4 vCPU sandbox, billed by the second until it is deleted. With no job, or "status", checks on jobs you offloaded.
argument-hint: "<job to run> | status"
disable-model-invocation: true
---

Offload this job to a Prized sandbox, so it keeps running off this machine:

$ARGUMENTS

Use the Prized sandbox tools from this plugin's `sandboxes` MCP server. If they are not available, tell the user to check `/mcp` (the server needs Node.js 20 or later and a Prized API key) and stop.

## Check on offloaded jobs

If the text above is empty or `status`, run `list_sandboxes` with `labels: {"prized-plugin": "offload"}`. For each one, `run_command` `cat ~/job/exit 2>/dev/null; tail -n 30 ~/job/log; find "$(cat ~/job/dir)" -newer ~/job/dir -type f | head -20` and report whether the job is still running or finished (no `~/job/exit` file means it is still running), with its exit code and the end of its log. The last part lists the files the job wrote. For a finished job, say that its sandbox keeps billing until it is deleted, offer to `download` those files, and then `delete_sandbox` it; delete only when the user says so. Stop here.

## Start a job

1. **Cost first.** Say in one line: one sandbox of 4 vCPU and 8 GB at \$0.261 an hour (2 vCPU and 4 GB at \$0.131 on the free credit, which also stops it after 60 minutes), billed by the second from the user's Prized balance until it is deleted, not just while the job runs (https://prized.dev/pricing). Then go on.
2. **Check what will be copied.** `upload` sends what git would commit: tracked files, and untracked ones `.gitignore` doesn't exclude. Outside a git repository it sends everything except `.git`, `node_modules` and virtualenvs. If a `.env*`, `*.pem`, `*.key` or other credentials file would go, ask the user before uploading. If the job needs a secret, ask the user for it now: it goes in `env_vars` at create (the value passes through this conversation), never in a command.
3. **Create.** `create_sandbox` with `auto_pause_minutes: 0` (otherwise an idle sandbox pauses and the job with it), `max_runtime_minutes` set to what the job needs plus a margin (240 if unsure, at most 60 on the free credit) so it can never bill past that, and `labels: {"prized-plugin": "offload", "job": "<a short slug>"}`. Use the `prized-base-v1` template (Python 3, Node.js 22, git, build tools) unless the job needs more.
4. **Copy the project.** `upload` the project directory to `/home/prized/work/<project>`.
5. **Install in the foreground.** Install what the job needs with `run_command` (for example `npm ci`, or `pip install -r requirements.txt` into a venv; there is no sudo), so a setup failure shows now and not after the user has left.
6. **Start it in the background.** `write_file` the job's command to `~/job/run.sh`, then `run_command` `echo /home/prized/work/<project> > ~/job/dir && cd /home/prized/work/<project> && nohup bash -c 'bash ~/job/run.sh; echo $? > ~/job/exit' > ~/job/log 2>&1 &`, then `sleep 5; tail -n 20 ~/job/log` to show it started.
7. **Hand over.** Tell the user the sandbox id; that the job keeps running if they close the laptop or quit Claude Code; what it costs an hour; that the sandbox keeps billing after the job ends until it is deleted, at the latest when its max runtime ends, and so the most it can cost if they never come back; and that `/prized:offload status` checks on it and brings the results back.

If a tool answers with a free-tier limit, follow what it says. If it answers that the Prized API key is missing or refused, tell the user to run `/plugin`, open Prized on the Installed tab, choose Configure options and paste a key from https://prized.dev/dashboard/workspace/api-keys (or export `PRIZED_API_KEY` and restart Claude Code), and stop.

To hand a whole Claude Code session to a machine that stays on, not just one job, use a Prized box: https://prized.dev/docs/keep-claude-code-running
