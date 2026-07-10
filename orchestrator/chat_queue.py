"""File-based task queue bridging the chat brain (producer) to the factory
(consumer). The chat brain can't hand a ticket to the factory through Slack
(the factory ignores bot messages), so instead it drops a JSON task file here
and the orchestrator's poll loop drains it alongside the Slack triggers.

Enqueue from the shell (this is what the chat brain runs):
    python -m orchestrator.chat_queue "build: add a /health endpoint"
"""
import json
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("chat-queue")

QUEUE_DIR = Path(__file__).resolve().parent.parent / "chat_queue"
PREFIXES = {"build:": "Feature", "fix:": "Bug", "task:": "Task"}


def enqueue(text: str) -> str:
    """Write one task file; returns the ticket key."""
    QUEUE_DIR.mkdir(exist_ok=True)
    text = text.strip()
    lowered = text.lower()
    ttype = "Task"                                  # default when no prefix
    for prefix, t in PREFIXES.items():
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            ttype = t
            break
    ts = f"{time.time():.6f}"
    key = f"CHAT-{ts.replace('.', '')[-8:]}"
    lines = text.splitlines()
    ticket = {
        "key": key,
        "summary": lines[0][:120] if lines else "untitled",
        "description": text,
        "type": ttype,
    }
    (QUEUE_DIR / f"{ts}.json").write_text(json.dumps(ticket))
    return key


def drain() -> list[dict]:
    """Return all queued tickets (oldest first) and remove their files."""
    if not QUEUE_DIR.exists():
        return []
    tickets = []
    for f in sorted(QUEUE_DIR.glob("*.json")):
        try:
            tickets.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            log.warning("Skipping bad queue file: %s", f.name)
        try:
            f.unlink()
        except OSError:
            pass
    return tickets


if __name__ == "__main__":
    body = " ".join(sys.argv[1:]).strip()
    if not body:
        print("usage: python -m orchestrator.chat_queue "
              "'<build|fix|task>: description'")
        sys.exit(1)
    print(f"Enqueued {enqueue(body)} for the factory.")
