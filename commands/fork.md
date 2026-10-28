---
description: Set this project up once in a Prized sandbox, fork it into live copies, try a different approach in each, and keep the one that passes. Each sandbox is about $0.13 an hour, billed by the second, and all are deleted at the end.
argument-hint: "[copies] <what to try>"
disable-model-invocation: true
---

Try several approaches to this task in parallel copies of one Prized sandbox, then bring the winner back:

$ARGUMENTS

Use the Prized sandbox tools from this plugin's `sandboxes` MCP server. If they are not available, tell the user to check `/mcp` (the server needs Node.js 20 or later and a Prized API key) and stop. If the text above starts with a number, that is how many copies to make; otherwise make 3. Make at most 8 unless the user asked for more.

1. **Plan.** Write one line for each approach, each genuinely different, and name the check that picks the winner: a test command, a benchmark, or a script whose exit code or number decides. Pick a short slug for this run. Then state the cost in one line: the parent and each copy are 2 vCPU and 4 GB at \$0.131 an hour while running (https://prized.dev/pricing), billed by the second, so a parent and 3 copies for 10 minutes is about 9 cents. Then go on; the user asked for this by running the command.
2. **Check what will be copied.** `upload` sends what git would commit: tracked files, and untracked ones `.gitignore` doesn't exclude. Outside a git repository it sends everything except `.git`, `node_modules` and virtualenvs. If a `.env*`, `*.pem`, `*.key` or other credentials file would go, ask the user before uploading.
3. **Set up once.** `create_sandbox` with `vcpu: 2`, `memory_gb: 4`, `max_runtime_minutes: 60` and `labels: {"prized-plugin": "fork", "run": "<slug>"}` (a bigger shape only if the check needs it, and say what it costs). `upload` the project directory to `/home/prized/work/<project>`, then run `git init -q && git add -A && git -c user.name=prized -c user.email=prized@localhost commit -qm base` there (an upload never includes `.git`) so each copy can show what it changed. Install dependencies, write the check to `~/check.sh` with `write_file`, and run it once on the unchanged code as the baseline.
4. **Fork.** `fork_sandbox` with the number of copies. Every copy starts with the parent's files, installed packages and running processes, so there is nothing to set up again.
5. **Try.** In each copy, make one approach's changes (`write_file`, or `run_command` for edits by script), then start the check in the background so the copies all run it at once: `run_command` `nohup bash -c 'SECONDS=0; bash ~/check.sh; echo "$? $SECONDS" > ~/check.exit' > ~/check.log 2>&1 &`. Once every copy has started, collect each result with `run_command` `for i in $(seq 100); do [ -f ~/check.exit ] && break; sleep 2; done; cat ~/check.exit; tail -n 20 ~/check.log` (the exit code, then the seconds it took).
6. **Compare.** Show a Markdown table with a row for the baseline and one for each approach: what it does, the check's result, and how long the check took. Pick the winner by the check, not by taste. If none passes, say so and leave the local project unchanged.
7. **Bring the winner back.** In the winning copy, `run_command` `git add -A && git diff --cached --stat && git diff --cached --name-status`, and print the diff. Name the files, then `download` each added or modified one into the project with `overwrite: true`. For a file the winner deleted, tell the user, and delete it locally only if they agree.
8. **Clean up.** `delete_sandbox` the parent and every copy, then `list_sandboxes` with `labels: {"run": "<slug>"}` to show none is left (a sandbox in state `deleting` is gone). End with how many sandboxes ran, for how long (from the create and fork times you saw to now), and what that cost at the rate above.

If a tool answers with a free-tier limit, follow what it says (the free credit runs a parent and up to 9 copies of 2 vCPU for 60 minutes). If it answers that the Prized API key is missing or refused, tell the user to run `/plugin`, open Prized on the Installed tab, choose Configure options and paste a key from https://prized.dev/dashboard/workspace/api-keys (or export `PRIZED_API_KEY` and restart Claude Code), and stop.
