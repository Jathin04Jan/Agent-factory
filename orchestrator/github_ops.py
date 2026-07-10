"""GitHub operations via the gh CLI (already authenticated on the VM)."""
import json
import logging
import subprocess
import time

from . import config

log = logging.getLogger("github")


def _sh(cmd: str, cwd=None, timeout=600) -> subprocess.CompletedProcess:
    log.info("$ %s", cmd)
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


def push_branch(workdir: str, branch: str) -> None:
    r = _sh(f"git push -u origin {branch} --force-with-lease", cwd=workdir)
    if r.returncode != 0:
        raise RuntimeError(f"Push failed: {r.stderr[-1000:]}")


def create_pr(workdir: str, branch: str, title: str, body: str) -> str:
    """Open a PR against DEFAULT_BRANCH. Returns the PR URL."""
    r = _sh(
        f'gh pr create --repo {config.GITHUB_REPO} --base {config.DEFAULT_BRANCH} '
        f'--head {branch} --title "{title}" --body "{body}"',
        cwd=workdir,
    )
    if r.returncode != 0:
        # PR may already exist from a previous fix attempt
        existing = _sh(f"gh pr view {branch} --repo {config.GITHUB_REPO} "
                       f"--json url -q .url", cwd=workdir)
        if existing.returncode == 0 and existing.stdout.strip():
            return existing.stdout.strip()
        raise RuntimeError(f"PR creation failed: {r.stderr[-1000:]}")
    return r.stdout.strip().splitlines()[-1]


def wait_for_checks(branch: str, poll_seconds: int = 60,
                    timeout_minutes: int = 90) -> str:
    """Poll until CI settles. Returns 'success', 'failure', or 'timeout'."""
    deadline = time.time() + timeout_minutes * 60
    time.sleep(30)  # give CI a moment to register the push
    while time.time() < deadline:
        r = _sh(f"gh pr view {branch} --repo {config.GITHUB_REPO} "
                f"--json statusCheckRollup")
        if r.returncode == 0:
            try:
                checks = json.loads(r.stdout).get("statusCheckRollup") or []
                states = {(c.get("conclusion") or c.get("state") or "PENDING").upper()
                          for c in checks}
                if states & {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED"}:
                    return "failure"
                if checks and states <= {"SUCCESS", "NEUTRAL", "SKIPPED"}:
                    return "success"
            except json.JSONDecodeError:
                pass
        time.sleep(poll_seconds)
    return "timeout"


def failed_check_logs(branch: str, max_chars: int = 12000) -> str:
    """Grab logs of the most recent failed workflow run on the branch."""
    r = _sh(f"gh run list --repo {config.GITHUB_REPO} --branch {branch} "
            f"--limit 5 --json databaseId,conclusion")
    try:
        runs = json.loads(r.stdout)
    except (json.JSONDecodeError, TypeError):
        return "Could not list workflow runs."
    for run in runs:
        if run.get("conclusion") == "failure":
            logs = _sh(f"gh run view {run['databaseId']} "
                       f"--repo {config.GITHUB_REPO} --log-failed")
            return logs.stdout[-max_chars:] or "No failure logs available."
    return "No failed runs found (failure may be an external check like SonarCloud)."


def merge_pr(branch: str) -> bool:
    r = _sh(f"gh pr merge {branch} --repo {config.GITHUB_REPO} "
            f"--{config.MERGE_METHOD} --delete-branch --admin")
    if r.returncode != 0:
        log.error("Merge failed: %s", r.stderr[-1000:])
        return False
    return True
