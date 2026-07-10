# Agent Factory — Setup Guide (Ubuntu VM)

End-to-end flow: **Jira ticket → Claude Code writes the fix → sandbox preview your team tests → Slack "approve" → push → PR → CI self-heal → auto-merge → your existing CI/CD deploys.**

You said the VM already has Claude Code installed and is logged into GitHub — steps 1–2 just verify that.

---

## Step 1 — Verify prerequisites on the VM

```bash
claude --version          # Claude Code installed
claude -p "say hello"     # confirms it's authenticated and runs headless
gh auth status            # GitHub CLI logged in
git --version
docker --version && docker compose version
python3 --version         # need 3.10+
```

Fix anything missing:

```bash
# gh CLI (if missing)
sudo apt update && sudo apt install -y gh git python3-venv python3-pip
gh auth login             # choose GitHub.com → HTTPS → login with browser

# Docker (if missing)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

**Important:** `gh auth status` must show a token with `repo` and `workflow` scopes. If you plan to use auto-merge with `--admin` (bypasses the 1-review branch protection), the account also needs admin rights on the repo. Run `gh auth refresh -h github.com -s repo,workflow` if scopes are missing.

---

## Step 2 — Get your three tokens

### 2a. Jira API token
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. **Create API token** → name it `agent-factory` → copy it.
3. You'll also need your Jira email and site URL (e.g. `https://yourorg.atlassian.net`).

### 2b. Slack bot
1. Go to https://api.slack.com/apps → **Create New App** → *From scratch* → name `Agent Factory`, pick your workspace.
2. **OAuth & Permissions** → *Bot Token Scopes* → add:
   - `chat:write`
   - `channels:history` (and `groups:history` if the channel is private)
3. **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-...`).
4. In Slack, create/pick a channel (e.g. `#agent-factory`), then **invite the bot**: `/invite @Agent Factory`.
5. Get the channel ID: channel name → *View channel details* → bottom of the About tab (`C0…`).

No webhooks, no inbound ports — the orchestrator only polls outbound. Nothing to open on the office firewall except the sandbox preview port you already planned to expose.

### 2c. GitHub
Already done — the orchestrator uses the `gh` CLI's existing login.

---

## Step 3 — Install the orchestrator

Copy the `agent-factory/` folder to the VM (scp, git, USB — whatever), then:

```bash
sudo mkdir -p /opt/agent-factory && sudo chown $USER /opt/agent-factory
cp -r agent-factory/* /opt/agent-factory/
cd /opt/agent-factory

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env    # fill in every value — see notes below
```

`.env` notes:
- `GITHUB_REPO` — `owner/repo` of the codebase the agent works on.
- `DEFAULT_BRANCH` — the branch PRs target (`develop` per your coworker's pipeline).
- `SANDBOX_URL` — `http://<VM-IP>:<port>` your team will open. The port is whatever the repo's `docker-compose.yml` exposes.
- `SANDBOX_UP_CMD` — adjust if the repo starts differently (e.g. `docker compose -f docker-compose.dev.yml up -d --build`).
- `VERIFY_CMD` — optional but recommended, e.g. `./gradlew compileJava test` or `yarn tsc --noEmit && yarn lint`. Runs before the preview goes up.
- `PROTECTED_PATHS` — files the agent must never touch. Add your infra/terraform paths.

---

## Step 4 — Prepare the target repo for the agent

Two things make the agent dramatically better:

1. **Add a `CLAUDE.md` at the repo root** describing: architecture overview, module layout, how to run tests, code conventions, and anything tribal ("auth lives in module X, never edit generated files in Y"). Claude Code reads it automatically at the start of every session.
2. **Enforce a Jira ticket template** for `ai-agent` tickets: expected behavior, steps to reproduce (bugs) or acceptance criteria (features), affected module if known. Ticket quality = prompt quality.

---

## Step 5 — Set up the Jira trigger

1. Create a label `ai-agent` (labels are free-form — just add it to a ticket).
2. The orchestrator picks up anything matching the JQL in `.env`:
   `labels = "ai-agent" AND status = "To Do"`
3. Make sure your project's workflow has statuses matching `JIRA_STATUS_IN_PROGRESS` and `JIRA_STATUS_DONE` (rename in `.env` if yours differ, e.g. "Selected for Development").

So the trigger is simply: **add the `ai-agent` label to a To Do ticket.** Remove the label to keep the agent away from a ticket.

---

## Step 6 — Test each integration on its own

Run these from `/opt/agent-factory` with the venv active:

```bash
# Jira: should list your labeled tickets
python3 -c "from orchestrator import jira_client; print(jira_client.fetch_ready_tickets())"

# Slack: should post a message in your channel
python3 -c "from orchestrator import slack_client; slack_client.post('agent factory online :factory:')"

# GitHub: should print repo info
gh repo view $(grep ^GITHUB_REPO .env | cut -d= -f2)

# Claude Code headless from Python:
python3 -c "from orchestrator import agent_runner; print(agent_runner.run_claude('What language is this project written in? Answer in one line.', '/tmp'))"
```

Fix any failures before continuing — every later problem is easier to debug when you know the four integrations work individually.

---

## Step 7 — First supervised run

1. Create a **trivial** test ticket, e.g. *"Fix typo on the login page: 'Welcom' → 'Welcome'"*, label it `ai-agent`, status To Do.
2. Run the orchestrator in the foreground so you can watch:

```bash
cd /opt/agent-factory && source venv/bin/activate
python -m orchestrator.main
```

3. Watch the full loop: Slack "picked up" → coding (a few minutes) → preview link in Slack → open it, check the fix → reply **approve** in the thread → PR opens → CI runs → merge → deployment pipeline fires.
4. If CI fails, watch the fix loop do its thing (max 3 attempts, then it escalates to Slack).

Do this with 3–5 increasingly hard tickets before trusting it unattended.

---

## Step 8 — Run it as a service

```bash
sudo cp agent-factory.service /etc/systemd/system/
sudo nano /etc/systemd/system/agent-factory.service   # set YOUR_USERNAME (twice)
sudo systemctl daemon-reload
sudo systemctl enable --now agent-factory

# Follow logs
journalctl -u agent-factory -f
```

---

## Step 9 — Decide the branch-protection question explicitly

Your coworker's pipeline requires 1 human PR approval. Options:

| Option | How | Trade-off |
|---|---|---|
| **A. Keep it (recommended to start)** | Set `AUTO_MERGE=false`. Agent posts the green PR to Slack; a human clicks merge. | One extra click; full audit trail. |
| B. Admin bypass | `AUTO_MERGE=true` (current code uses `gh pr merge --admin`). | Needs repo admin; review gate is bypassed for agent PRs. |
| C. Bot reviewer | A second bot account auto-approves agent PRs. | Satisfies the rule technically, defeats its spirit. |

Since your real human gate is the Slack preview approval, B is defensible — but start with A until the agent has earned trust.

---

## Guardrails already built in

- Only tickets with the `ai-agent` label are ever touched.
- One ticket at a time; fresh clone per ticket (no state bleeding between jobs).
- Agent can't push or open PRs itself — the orchestrator does, only after Slack approval.
- Protected-paths diff check: if the agent touched `.github/`, hooks, infra, etc., the run is halted and escalated.
- Fix loop capped at `MAX_FIX_ATTEMPTS`, session capped by `CLAUDE_MAX_TURNS` and a wall-clock timeout.
- Everything escalates to Slack instead of failing silently.

## Known v1 limitations (by design — add later)

- Serial processing (one ticket at a time). Parallel needs per-ticket ports + compose project names.
- Approval is "anyone in the channel who types approve" — restrict to specific Slack user IDs in `slack_client.wait_for_approval` when you care.
- Sonar/CodeQL-style external checks report status but their detailed findings aren't fed to the fix loop yet (only GitHub Actions logs are). SonarCloud API integration is the natural next step.
- Secrets live in `.env` on the VM — fine for a pilot, use a secrets manager beyond that.
