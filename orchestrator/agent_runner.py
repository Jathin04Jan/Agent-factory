"""Runs Claude Code in headless mode inside a ticket workspace."""
import json
import logging
import subprocess

from . import config

log = logging.getLogger("agent")


def run_claude(prompt: str, cwd: str) -> tuple[bool, str]:
    """Execute one headless Claude Code session. Returns (success, result_text).

    Uses --dangerously-skip-permissions because this runs unattended on a
    dedicated VM inside a throwaway git clone. The blast radius is limited by:
    the orchestrator's protected-paths diff check, the Slack approval gate,
    and CI. Do not run this on a machine you care about.
    """
    cmd = [
        config.CLAUDE_BIN, "-p", prompt,
        "--output-format", "json",
        "--max-turns", str(config.CLAUDE_MAX_TURNS),
        "--dangerously-skip-permissions",
    ]
    log.info("Starting Claude Code session in %s", cwd)
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=config.CLAUDE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, "Claude Code session timed out"

    if proc.returncode != 0:
        return False, f"Claude Code exited {proc.returncode}: {proc.stderr[-2000:]}"

    try:
        data = json.loads(proc.stdout)
        result = data.get("result", "")
        if data.get("is_error"):
            return False, result or "Claude Code reported an error"
        log.info("Session done — cost: $%s, turns: %s",
                 data.get("total_cost_usd", "?"), data.get("num_turns", "?"))
        return True, result
    except (json.JSONDecodeError, TypeError):
        # Fall back to raw output if the JSON envelope changes
        return True, proc.stdout[-4000:]
