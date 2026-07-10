"""Slack-prompt trigger mode (TRIGGER=slack) — no Jira needed.

Post a message in the factory channel starting with one of:
    build: <what you want built>
    fix: <what's broken>
    task: <anything else>

Everything after the prefix becomes the ticket. Extra lines = description.
A cursor file remembers the last processed message so restarts don't
re-run old requests.
"""
import logging
import time
from pathlib import Path

import requests

from . import config

log = logging.getLogger("slack-trigger")
HEADERS = {"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"}
API = "https://slack.com/api"
CURSOR_FILE = Path(__file__).resolve().parent.parent / ".slack_cursor"
PREFIXES = {"build:": "Feature", "fix:": "Bug", "task:": "Task"}


def _read_cursor() -> str:
    if CURSOR_FILE.exists():
        return CURSOR_FILE.read_text().strip()
    # First run: start from "now" so old channel history is ignored
    now = f"{time.time():.6f}"
    CURSOR_FILE.write_text(now)
    return now


def _write_cursor(ts: str) -> None:
    CURSOR_FILE.write_text(ts)


def fetch_new_tasks() -> list[dict]:
    """Return new prompt-messages as ticket dicts, oldest first."""
    cursor = _read_cursor()
    r = requests.get(
        f"{API}/conversations.history", headers=HEADERS,
        params={"channel": config.SLACK_CHANNEL_ID, "oldest": cursor,
                "inclusive": "false", "limit": 20},
        timeout=30,
    )
    data = r.json()
    if not data.get("ok"):
        log.error("Slack history failed: %s", data.get("error"))
        return []

    tickets = []
    newest_ts = cursor
    for msg in sorted(data.get("messages", []), key=lambda m: float(m["ts"])):
        newest_ts = max(newest_ts, msg["ts"], key=float)
        if msg.get("bot_id") or msg.get("subtype"):
            continue                                   # humans only
        text = (msg.get("text") or "").strip()
        lowered = text.lower()
        for prefix, ttype in PREFIXES.items():
            if lowered.startswith(prefix):
                body = text[len(prefix):].strip()
                lines = body.splitlines()
                tickets.append({
                    "key": f"SLACK-{msg['ts'].replace('.', '')[-8:]}",
                    "summary": lines[0][:120] if lines else "untitled",
                    "description": body,
                    "type": ttype,
                })
                break
    if newest_ts != cursor:
        _write_cursor(newest_ts)
    return tickets
