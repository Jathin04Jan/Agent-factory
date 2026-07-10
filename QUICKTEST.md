# Quick Test — Slack-Prompt Mode (no Jira)

Goal: post `build: ...` in Slack → agent builds it on a dummy project →
you approve in Slack → it ships through PR + CI + merge.

## Step 1 — Push this folder to GitHub (from your laptop)

```bash
cd agent-factory
git init && git add . && git commit -m "agent factory v1"
gh repo create yourname/agent-factory --private --source=. --push
```

`.gitignore` already excludes `.env`, so no secrets can leak. Never commit `.env`.

## Step 2 — Generate the dummy target project (ChatDock)

One script, run on the VM. It has Claude Code build a containerized
messaging app (Spring Boot + Next.js + Postgres, tests, CI, CLAUDE.md files),
installs the subagents from `target-repo-kit/`, and pushes it to GitHub:

```bash
cd agent-factory/dummy-project
./create-dummy-project.sh yourname/chatdock
```

Spec lives in `DUMMY_PROJECT_SPEC.md` (multi-user login, user list, DMs —
with email invites etc. deliberately left out as future agent tasks).
To add the subagents to any OTHER repo later:
`target-repo-kit/install-agents.sh /path/to/repo --commit`

## Step 3 — Set up on the VM (Claude Code does it)

```bash
gh repo clone yourname/agent-factory && cd agent-factory
claude
```

Then give it this one prompt:

> Read CLAUDE.md and set up this project completely, step by step. Verify
> prerequisites first, then walk me through the values you need from me.

It will check the tooling, create the venv, ask you for the Slack token,
channel ID, and dummy repo name, write `.env`, test all integrations, and
launch the orchestrator.

## Step 4 — Prepare Slack (5 minutes, one-time)

If you don't have the bot yet: https://api.slack.com/apps → Create New App →
From scratch → **OAuth & Permissions** → bot scopes `chat:write` +
`channels:history` → **Install to Workspace** → copy the `xoxb-` token.
Create a channel like `#agent-factory` and `/invite` the bot.
(Claude Code will walk you through this during Step 3 anyway.)

## Step 5 — Fire a test task

In the Slack channel, post:

```
build: add a /health endpoint that returns {"status": "ok"} and the current time. Include a test.
```

Expected sequence in the thread:
1. 🤖 "Picked up SLACK-xxxx" — agent is coding (a few minutes)
2. 🧪 "ready for testing" + preview URL (or diff if no sandbox) — open it, poke around
3. You reply **approve** in the thread
4. ⬆️ PR link posted, CI running; if CI fails you'll see 🔧 fix attempts
5. ✅ merged

Then try a `fix:` — break something in the dummy app on purpose first.

## Notes for this test mode

- Only messages starting with `build:`, `fix:`, or `task:` trigger the agent.
  Everything else in the channel is ignored.
- Old messages are ignored — only things posted after the orchestrator
  starts count (cursor stored in `.slack_cursor`).
- One task at a time; queue more and they run in order.
- Anyone in the channel can approve. Fine for a test; lock down later.
- Switching to the full Jira pipeline later = set `TRIGGER=jira` in `.env`
  and fill the Jira variables (see SETUP.md).
