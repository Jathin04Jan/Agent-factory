# Agent Factory — Self-Setup Instructions for Claude Code

You are running on an Ubuntu VM inside a fresh clone of this repository.
Your job: set up and launch the Agent Factory orchestrator, interactively,
step by step. Ask the user for input where marked. Do not skip verification
steps. Do not commit or push anything from this repo — especially not `.env`.

## What this project is

A Python orchestrator that watches a Slack channel for messages like
`build: add a dark mode toggle`, then: clones a target repo, implements the
request using Claude Code headless, boots a docker-compose sandbox for human
testing, waits for a Slack "approve" reply, pushes a branch, opens a PR,
watches CI and self-heals failures, then merges. Modules live in
`orchestrator/`. Full docs: `SETUP.md` (Jira mode) and `QUICKTEST.md`
(this Slack-only test mode).

## Setup procedure — follow in order

### 1. Verify prerequisites
Run and show the user the results of:
- `claude --version`
- `gh auth status` (must be logged in; needs repo + workflow scopes)
- `git --version`, `docker --version`, `docker compose version`
- `python3 --version` (need 3.10+)

If anything is missing, install it (apt for git/python3-venv, official
script for docker, `gh auth login` for GitHub) and re-verify. If docker
requires sudo, add the user to the docker group and tell them to re-login.

### 2. Create the environment
```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
```

### 3. Fill in .env — ASK THE USER for each value
Keep `TRIGGER=slack`. Ask the user for:
- `SLACK_BOT_TOKEN` — from their Slack app (xoxb-...). If they haven't made
  one yet, walk them through it: api.slack.com/apps → Create New App →
  From scratch → OAuth & Permissions → bot scopes `chat:write` +
  `channels:history` → Install to Workspace → copy token → invite the bot
  to the channel with /invite.
- `SLACK_CHANNEL_ID` — channel details → About tab (starts with C).
- `GITHUB_REPO` — owner/name of the DUMMY TARGET repo the agent will work
  on (NOT this orchestrator repo).
- `DEFAULT_BRANCH` — the target repo's main working branch (check with
  `gh repo view <repo> --json defaultBranchRef`).
- `SANDBOX_URL` — http://<this VM's IP>:<port the target repo's
  docker-compose exposes>. Get the IP via `hostname -I`. If the target repo
  has no docker-compose.yml, set SANDBOX_UP_CMD and SANDBOX_DOWN_CMD to
  `true` (the literal shell no-op) and tell the user previews will be
  diff-only.
- Leave Jira variables empty. Set `WORK_DIR` to `<repo>/workspaces` if
  /opt is not writable, and `AUTO_MERGE=true` (it's a dummy project).

Write the values into `.env` yourself after collecting them.

### 4. Test each integration individually
Run these and fix failures before continuing:
```bash
# Slack — a message must appear in the channel
venv/bin/python -c "from orchestrator import slack_client; slack_client.post('agent factory online :factory:')"

# GitHub — target repo visible
gh repo view $(grep ^GITHUB_REPO .env | cut -d= -f2)

# Claude Code headless round-trip
venv/bin/python -c "from orchestrator import agent_runner; print(agent_runner.run_claude('Reply with exactly: FACTORY_OK', '/tmp'))"

# Config + trigger module load cleanly
venv/bin/python -c "from orchestrator import config, slack_trigger; print('config OK, trigger:', config.TRIGGER)"
```

### 5. Launch
Ask the user whether they want foreground (watch logs) or background:
- Foreground: `venv/bin/python -m orchestrator.main`
- Background: `nohup venv/bin/python -m orchestrator.main >> factory.log 2>&1 &`
  (or install agent-factory.service per SETUP.md step 8)

### 6. Tell the user how to use it
Post in the Slack channel:
- `build: <feature description>` or `fix: <bug description>`
- The bot replies when it picks the task up, then posts a preview/diff and
  waits for a reply containing **approve** (or **reject**) in that thread.
- After approve: push → PR → CI watch → auto-merge.

## Rules for you during setup
- Never print or log token values back to the user.
- Never `git add` / commit `.env`, `.slack_cursor`, `workspaces/`, `venv/`.
- If a step fails, diagnose and fix it before moving on; summarize what
  you changed.
