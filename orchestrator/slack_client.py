"""Slack notifications + thread-reply approval gate.

Approval model (v1, outbound-only — no Socket Mode, no inbound ports):
the bot posts a message, then polls the thread for a reply containing
'approve' or 'reject' from any human. Simple and firewall-friendly.
"""
import logging
import time

import requests

from . import config

log = logging.getLogger("slack")
HEADERS = {"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"}
API = "https://slack.com/api"


def post(text: str, thread_ts: str | None = None) -> str:
    """Post a message; returns its ts (usable as a thread id)."""
    payload = {"channel": config.SLACK_CHANNEL_ID, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    r = requests.post(f"{API}/chat.postMessage", headers=HEADERS,
                      json=payload, timeout=30)
    data = r.json()
    if not data.get("ok"):
        log.error("Slack post failed: %s", data.get("error"))
        return ""
    return data["ts"]


def wait_for_approval(thread_ts: str, poll_seconds: int = 20) -> str:
    """Block until someone replies 'approve' or 'reject' in the thread.

    Returns 'approved', 'rejected', or 'timeout'.
    """
    deadline = time.time() + config.APPROVAL_TIMEOUT_HOURS * 3600
    while time.time() < deadline:
        r = requests.get(
            f"{API}/conversations.replies", headers=HEADERS,
            params={"channel": config.SLACK_CHANNEL_ID, "ts": thread_ts},
            timeout=30,
        )
        data = r.json()
        if data.get("ok"):
            for msg in data.get("messages", [])[1:]:      # skip the parent
                if msg.get("bot_id"):
                    continue                               # ignore bot replies
                text = (msg.get("text") or "").lower()
                if "approve" in text:
                    return "approved"
                if "reject" in text:
                    return "rejected"
        time.sleep(poll_seconds)
    return "timeout"
