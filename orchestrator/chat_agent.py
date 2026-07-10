"""Conversational Slack brain for the Agent Factory.

Chat with the factory in plain English. This polls the channel for human
messages that are NOT factory commands (build:/fix:/task:) and NOT thread
replies, feeds each into a single persistent Claude Code session that has
full tool access on this VM, and posts the reply back to the channel.

Because the brain IS Claude Code (not a scripted menu), it can both answer
questions and actually act: start/stop the ChatDock app, check status, run
git/gh/docker, and dispatch code-change tasks to the factory pipeline via
`python -m orchestrator.chat_queue`.

Run:  python -m orchestrator.chat_agent
"""
import json
import logging
import subprocess
import time
import uuid
from pathlib import Path

import requests

from . import config
from . import slack_client as slack

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-6s %(levelname)-7s %(message)s",
)
log = logging.getLogger("chat")

HEADERS = {"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"}
API = "https://slack.com/api"
ROOT = Path(__file__).resolve().parent.parent
CURSOR_FILE = ROOT / ".chat_cursor"
SESSION_FILE = ROOT / ".chat_session"

# The target app the factory builds on (cloned here during setup).
CHATDOCK_DIR = "/home/jathin/chatdock"
FACTORY_PREFIXES = ("build:", "fix:", "task:")
POLL_SECONDS = 5
BRAIN_TIMEOUT = 900          # a message may trigger a docker build, so be generous
BRAIN_MAX_TURNS = 30

SYSTEM_PROMPT = f"""You are the Agent Factory foreman, chatting with your \
operator over Slack. Talk like a helpful teammate: concise, plain, and \
Slack-friendly. Use Slack mrkdwn only (*bold*, _italic_, `code`, ```blocks```) \
— never markdown headings, tables, or [links](url). Keep replies short unless \
asked for detail.

You run on the dedicated VM that hosts the factory, WITH full shell access \
(bash, git, gh, docker). Actually run commands to answer questions and to get \
things done — don't just describe what could be done.

Key locations:
- Factory repo (your working dir): {ROOT}
- ChatDock app (the project the factory builds on): {CHATDOCK_DIR}
  - Start:   (cd {CHATDOCK_DIR} && docker compose up -d --build)
  - Stop:    (cd {CHATDOCK_DIR} && docker compose down)
  - Restart: (cd {CHATDOCK_DIR} && docker compose restart)
  - Status:  (cd {CHATDOCK_DIR} && docker compose ps)
  - It serves at {config.SANDBOX_URL} (demo login: alice / demo1234)

Commanding the factory (the pipeline that writes code):
- To have the factory implement a code change on ChatDock, enqueue a task:
    {ROOT}/venv/bin/python -m orchestrator.chat_queue "build: <feature>"
  Use "build:" for features, "fix:" for bugs, "task:" for other changes.
- The factory then implements it and posts progress + a preview link in THIS \
Slack channel, and waits for someone to reply *approve* in that thread before \
it ships (PR -> CI -> merge). After you dispatch, tell the user to watch for \
the preview and reply *approve* in that thread.
- Do NOT edit ChatDock code yourself — always dispatch it to the factory so it \
goes through preview + approval.

When asked to start/stop/restart the app or check status: run the docker \
commands and report the real result. When asked for a code change: dispatch it \
to the factory and confirm you kicked it off. Otherwise: just chat and answer.

Never print secret values (tokens). Be honest about what you actually did and \
about anything that failed."""


def _read_cursor() -> str:
    if CURSOR_FILE.exists():
        return CURSOR_FILE.read_text().strip()
    now = f"{time.time():.6f}"          # first run: ignore old history
    CURSOR_FILE.write_text(now)
    return now


def _write_cursor(ts: str) -> None:
    CURSOR_FILE.write_text(ts)


def _fetch_new_messages() -> list[tuple[str, str]]:
    """New human, non-command, top-level messages as (ts, text), oldest first."""
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

    out = []
    newest = cursor
    for msg in sorted(data.get("messages", []), key=lambda m: float(m["ts"])):
        newest = max(newest, msg["ts"], key=float)
        if msg.get("bot_id") or msg.get("subtype"):
            continue                                # humans only, no bot echoes
        text = (msg.get("text") or "").strip()
        if not text or text.lower().startswith(FACTORY_PREFIXES):
            continue                                # commands belong to the factory
        out.append((msg["ts"], text))
    if newest != cursor:
        _write_cursor(newest)
    return out


def _run_brain(user_text: str) -> str:
    """Send one message to the persistent Claude Code session; return its reply."""
    session_id = SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else ""
    cmd = [
        config.CLAUDE_BIN, "-p", user_text,
        "--output-format", "json",
        "--append-system-prompt", SYSTEM_PROMPT,
        "--dangerously-skip-permissions",
        "--max-turns", str(BRAIN_MAX_TURNS),
        "--add-dir", CHATDOCK_DIR,
    ]
    if session_id:
        cmd += ["--resume", session_id]             # continue the conversation
    else:
        session_id = str(uuid.uuid4())
        cmd += ["--session-id", session_id]         # start a fresh one

    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=BRAIN_TIMEOUT)
    except subprocess.TimeoutExpired:
        return ":hourglass: That took too long and timed out — try again or narrow it down."
    if proc.returncode != 0:
        log.error("brain exited %s: %s", proc.returncode, proc.stderr[-800:])
        return ":warning: I hit an error working on that — check `chat.log`."

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.stdout[-1500:] or "(no reply)"
    SESSION_FILE.write_text(data.get("session_id", session_id))
    log.info("reply done — cost $%s, turns %s",
             data.get("total_cost_usd", "?"), data.get("num_turns", "?"))
    if data.get("is_error"):
        return data.get("result") or ":warning: Something went wrong."
    return (data.get("result") or "").strip() or "(no reply)"


def main() -> None:
    log.info("Chat brain online. Channel=%s, polling every %ss",
             config.SLACK_CHANNEL_ID, POLL_SECONDS)
    slack.post(":brain: *Chat brain online* — talk to me right here. Ask me "
               "anything, tell me to start/stop the app, or just describe a "
               "change you want built.")
    while True:
        try:
            for ts, text in _fetch_new_messages():
                log.info("user: %s", text[:150])
                slack.post(_run_brain(text))
        except Exception:
            log.exception("chat poll cycle failed")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
