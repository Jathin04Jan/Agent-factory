# Agent Factory

An autonomous software-delivery pipeline you drive from **Slack**. Ask for a
change in plain English and the factory clones the target repo, implements the
request with **Claude Code** (headless), boots a docker-compose sandbox for you
to test, waits for your **approve** reply in Slack, opens a PR, watches CI and
self-heals failures, then merges.

It ships with two ways to talk to it:

1. **Command mode** — post `build:`, `fix:`, or `task:` messages; each becomes a
   ticket the pipeline runs.
2. **Chat mode** — a conversational "brain" (`orchestrator/chat_agent.py`) you
   talk to like a normal assistant. It answers questions, runs ops on the VM
   (start/stop/restart the target app, check status), and dispatches code
   changes to the pipeline for you.

> ⚠️ **This is designed to run unattended on a dedicated, throwaway VM.** The
> agents run Claude Code with `--dangerously-skip-permissions` (full tool
> access). The chat brain will execute shell commands on the VM based on Slack
> messages. Do **not** run this on a machine you care about, and only expose it
> in a Slack channel you trust. See [Security](#security).

---

## How it works

```
         Slack channel
   ┌───────────────────────────┐
   │  "restart the app"         │──▶ chat brain (chat_agent.py)
   │  "add a /health endpoint"  │       │  chats, runs docker/gh/git,
   │  "build: add dark mode"    │       │  dispatches tasks ──┐
   └───────────────────────────┘                             ▼
                                              file queue (chat_queue.py)
                                                              │
   build:/fix:/task:  ──▶ slack_trigger.py ──┐                │
                                             ▼                ▼
                                     orchestrator/main.py  (the pipeline)
                                             │
       plan ─▶ implement ─▶ review ─▶ verify ─▶ sandbox preview ─▶ Slack
       "approve" gate ─▶ push branch ─▶ open PR ─▶ watch CI ─▶ self-heal ─▶ merge
```

### Modules (`orchestrator/`)

| File | Role |
|------|------|
| `main.py` | The pipeline loop: fetch tickets → plan/implement/review → preview → approve → PR → CI self-heal → merge. |
| `config.py` | Loads everything from `.env`. |
| `slack_trigger.py` | Turns `build:/fix:/task:` Slack messages into tickets (command mode). |
| `chat_agent.py` | The conversational brain (chat mode) — persistent Claude Code session bridged to Slack. |
| `chat_queue.py` | File queue the brain uses to hand code tasks to the pipeline. |
| `slack_client.py` | Outbound Slack posts + the thread-reply approval gate. |
| `agent_runner.py` | Runs one headless Claude Code session. |
| `github_ops.py` | Push, open PR, watch checks, merge (via `gh`). |
| `sandbox.py` | Workspace prep, docker-compose up/down, diff/verify. |
| `jira_client.py` | Optional Jira trigger source (see `SETUP.md`). |
| `prompts.py` | The architect / implement / review / fix prompts. |

---

## Prerequisites

Install and verify on the VM:

- **Claude Code** CLI — `claude --version` (authenticated)
- **GitHub CLI** — `gh auth status` (logged in, scopes `repo` + `workflow`)
- **Git** — `git --version`
- **Docker + Compose** — `docker --version`, `docker compose version`
- **Python 3.10+** — `python3 --version`

`gh` and the compose plugin can be installed without root:

```bash
# docker compose plugin (user-local)
mkdir -p ~/.docker/cli-plugins
curl -sSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o ~/.docker/cli-plugins/docker-compose && chmod +x ~/.docker/cli-plugins/docker-compose

# gh (user-local) — see https://github.com/cli/cli/releases
```

---

## Setup

```bash
# 1. Clone
gh repo clone <owner>/Agent-factory && cd Agent-factory

# 2. Python env
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. Config
cp .env.example .env
#    then edit .env — see the table below
```

### `.env` values

| Variable | What it is |
|----------|------------|
| `TRIGGER` | `slack` (prompt-driven, this guide) or `jira` (see `SETUP.md`). |
| `SLACK_BOT_TOKEN` | Your Slack app bot token (`xoxb-…`). Scopes: `chat:write`, `channels:history`. Install to workspace, `/invite` the bot to the channel. |
| `SLACK_CHANNEL_ID` | The channel ID (starts with `C`) — channel → About. |
| `GITHUB_REPO` | `owner/name` of the **target** repo the agent edits (not this repo). |
| `DEFAULT_BRANCH` | Target repo's main branch (`gh repo view <repo> --json defaultBranchRef`). |
| `SANDBOX_URL` | `http://<VM-IP>:<port>` the target's docker-compose exposes. |
| `WORK_DIR` | Where clones live (default `/opt/agent-factory/workspaces`; use a writable path). |
| `AUTO_MERGE` | `true` to merge automatically once CI is green. |
| Jira vars | Leave empty in Slack mode. |

If the target repo has no docker-compose, set `SANDBOX_UP_CMD` and
`SANDBOX_DOWN_CMD` to `true` (a no-op) — previews become diff-only.

### A target repo to play with

This repo includes a generator for a dummy target app (**ChatDock** — a
containerized Spring Boot + Next.js + Postgres messaging app):

```bash
cd dummy-project
./create-dummy-project.sh <owner>/chatdock     # builds it with Claude Code and pushes it
```

Point `GITHUB_REPO` at the repo it creates. Spec: `dummy-project/DUMMY_PROJECT_SPEC.md`.

### Verify integrations

```bash
# Slack (a message should appear in the channel)
venv/bin/python -c "from orchestrator import slack_client; slack_client.post('agent factory online')"
# GitHub target repo visible
gh repo view $(grep ^GITHUB_REPO .env | cut -d= -f2)
# Claude Code round-trip
venv/bin/python -c "from orchestrator import agent_runner; print(agent_runner.run_claude('Reply with exactly: FACTORY_OK', '/tmp'))"
# Config loads
venv/bin/python -c "from orchestrator import config; print('trigger:', config.TRIGGER)"
```

---

## Running

The pipeline and the chat brain are two long-running processes. Run whichever
you want (the brain is optional; the pipeline works on its own).

```bash
# The pipeline (required) — foreground:
venv/bin/python -m orchestrator.main
#   …or background:
nohup venv/bin/python -m orchestrator.main >> factory.log 2>&1 &

# The chat brain (optional) — full-tool-access conversational agent:
nohup venv/bin/python -m orchestrator.chat_agent >> chat.log 2>&1 &
```

For a systemd unit, see `agent-factory.service` and `SETUP.md` (step 8).

---

## Using it

In your Slack channel:

**Command mode** — the message becomes a ticket:
```
build: add a /health endpoint that returns {"status":"ok"} and the time. Include a test.
fix: the login button is misaligned on mobile
task: bump the postgres image to 16
```
`build:` = feature (plan → implement → review). `fix:`/`task:` = single-pass.

**Chat mode** (if the brain is running) — just talk, no prefix:
```
is the app running? what's on port 3000?
restart the app
add an email-invite feature to chatdock — mock the actual send
```
The brain answers, runs ops itself, or dispatches code changes to the pipeline.

**The approval gate:** for any code change the factory posts a preview link
(or a diff) and waits. Reply **approve** in that thread to ship (push → PR →
CI → merge) or **reject** to stop. Only messages *after* startup are read; a
cursor file (`.slack_cursor` / `.chat_cursor`) remembers your place.

---

## Security

This system is intentionally high-privilege and is meant for a **dedicated,
disposable VM**:

- Agents run Claude Code with `--dangerously-skip-permissions`.
- The **chat brain executes shell commands on the VM based on Slack messages** —
  anyone who can post in the configured channel can drive it. Keep the channel
  private and trusted.
- Guardrails that remain in place: the pipeline's protected-paths diff check,
  the Slack **approve** gate before any push, and CI before merge.
- **Never commit `.env`** (it holds your bot token). It is gitignored, along
  with `.chat_cursor`, `.chat_session`, `chat_queue/`, `workspaces/`, and logs.

To restrict the brain to yourself, add an allowlist on the Slack user ID in
`chat_agent.py` (`_fetch_new_messages`) so it ignores everyone else.

---

## Modes & further docs

- **Slack mode** (this README, `QUICKTEST.md`) — prompt-driven, no Jira.
- **Jira mode** (`SETUP.md`) — set `TRIGGER=jira`, fill the Jira vars; tickets
  labeled for the agent drive the same pipeline.
- **Subagent kit** (`target-repo-kit/`) — installs `code-explorer`,
  `code-reviewer`, `test-writer` subagents into any target repo.

## Troubleshooting

- **Nothing happens on a Slack post** — bot not invited to the channel, wrong
  `SLACK_CHANNEL_ID`, or the message predates startup. Only `build:/fix:/task:`
  (or, in chat mode, any non-command message) trigger anything.
- **Push/PR fails** — `gh auth status` missing the `workflow` scope:
  `gh auth refresh -h github.com -s workflow`.
- **Sandbox preview never comes up** — check the target repo's
  `docker compose up` works by hand and that `SANDBOX_URL`'s port matches.
- **Brain seems stuck** — check `chat.log`; a message that triggers a docker
  build can take a while.
