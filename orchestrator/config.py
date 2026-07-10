"""Central configuration — everything comes from the .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env sitting next to the project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _req(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


# --- Trigger source: "jira" (label-driven) or "slack" (prompt-driven) ---
TRIGGER = os.getenv("TRIGGER", "jira").lower()

# --- Jira (only required when TRIGGER=jira) ---
_jreq = _req if TRIGGER == "jira" else (lambda n: os.getenv(n, ""))
JIRA_BASE_URL = _jreq("JIRA_BASE_URL").rstrip("/")         # https://yourorg.atlassian.net
JIRA_EMAIL = _jreq("JIRA_EMAIL")
JIRA_API_TOKEN = _jreq("JIRA_API_TOKEN")
JIRA_JQL = os.getenv(
    "JIRA_JQL",
    'labels = "ai-agent" AND status = "To Do" ORDER BY created ASC',
)
JIRA_POLL_SECONDS = int(os.getenv("JIRA_POLL_SECONDS", "45"))
JIRA_STATUS_IN_PROGRESS = os.getenv("JIRA_STATUS_IN_PROGRESS", "In Progress")
JIRA_STATUS_DONE = os.getenv("JIRA_STATUS_DONE", "Done")

# --- GitHub ---
GITHUB_REPO = _req("GITHUB_REPO")                          # owner/repo
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "develop")
AUTO_MERGE = os.getenv("AUTO_MERGE", "true").lower() == "true"
MERGE_METHOD = os.getenv("MERGE_METHOD", "squash")         # squash | merge | rebase

# --- Slack ---
SLACK_BOT_TOKEN = _req("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = _req("SLACK_CHANNEL_ID")
APPROVAL_TIMEOUT_HOURS = float(os.getenv("APPROVAL_TIMEOUT_HOURS", "24"))

# --- Workspace / sandbox ---
WORK_DIR = Path(os.getenv("WORK_DIR", "/opt/agent-factory/workspaces"))
SANDBOX_UP_CMD = os.getenv("SANDBOX_UP_CMD", "docker compose up -d --build")
SANDBOX_DOWN_CMD = os.getenv("SANDBOX_DOWN_CMD", "docker compose down -v")
SANDBOX_URL = os.getenv("SANDBOX_URL", "http://localhost:3000")  # link posted to Slack
VERIFY_CMD = os.getenv("VERIFY_CMD", "")                   # e.g. "./gradlew test" — optional

# --- Claude Code ---
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
CLAUDE_MAX_TURNS = int(os.getenv("CLAUDE_MAX_TURNS", "80"))
CLAUDE_TIMEOUT_SECONDS = int(os.getenv("CLAUDE_TIMEOUT_SECONDS", "3600"))

# --- Phased pipeline (plan -> implement -> review) ---
# Ticket types that get the full 3-phase treatment; others run single-phase.
PHASED_TYPES = [t.strip().lower() for t in
                os.getenv("PHASED_TYPES", "feature,story,new feature").split(",")]
MAX_REVIEW_CYCLES = int(os.getenv("MAX_REVIEW_CYCLES", "2"))

# --- Guardrails ---
MAX_FIX_ATTEMPTS = int(os.getenv("MAX_FIX_ATTEMPTS", "3"))
PROTECTED_PATHS = [
    p.strip() for p in os.getenv(
        "PROTECTED_PATHS", ".github/,.githooks/,infra/,Dockerfile,docker-compose"
    ).split(",") if p.strip()
]
