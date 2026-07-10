"""Workspace + Docker sandbox management for one ticket at a time."""
import logging
import shutil
import subprocess

from . import config

log = logging.getLogger("sandbox")


def _sh(cmd: str, cwd=None, timeout=1800) -> subprocess.CompletedProcess:
    log.info("$ %s", cmd)
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


def prepare_workspace(ticket_key: str) -> tuple[str, str]:
    """Fresh clone + feature branch. Returns (workdir, branch)."""
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    workdir = config.WORK_DIR / ticket_key.lower()
    if workdir.exists():
        shutil.rmtree(workdir)

    branch = f"agent/{ticket_key.lower()}"
    r = _sh(f"gh repo clone {config.GITHUB_REPO} {workdir} -- "
            f"--branch {config.DEFAULT_BRANCH} --single-branch")
    if r.returncode != 0:
        raise RuntimeError(f"Clone failed: {r.stderr[-1000:]}")
    _sh(f"git checkout -b {branch}", cwd=workdir)
    return str(workdir), branch


def has_commits(workdir: str) -> bool:
    r = _sh(f"git rev-list --count origin/{config.DEFAULT_BRANCH}..HEAD",
            cwd=workdir)
    return r.returncode == 0 and int(r.stdout.strip() or 0) > 0


def touched_protected_paths(workdir: str) -> list[str]:
    """Files changed on the branch that fall under PROTECTED_PATHS."""
    r = _sh(f"git diff --name-only origin/{config.DEFAULT_BRANCH}...HEAD",
            cwd=workdir)
    changed = [f for f in r.stdout.splitlines() if f.strip()]
    return [f for f in changed
            if any(f.startswith(p) or p in f for p in config.PROTECTED_PATHS)]


def run_verify(workdir: str) -> tuple[bool, str]:
    """Optional orchestrator-side verification (VERIFY_CMD in .env)."""
    if not config.VERIFY_CMD:
        return True, "no VERIFY_CMD configured — skipped"
    r = _sh(config.VERIFY_CMD, cwd=workdir, timeout=2400)
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def up(workdir: str) -> bool:
    r = _sh(config.SANDBOX_UP_CMD, cwd=workdir, timeout=1800)
    if r.returncode != 0:
        log.error("Sandbox up failed: %s", r.stderr[-1500:])
        return False
    return True


def down(workdir: str) -> None:
    _sh(config.SANDBOX_DOWN_CMD, cwd=workdir, timeout=600)


def diff_summary(workdir: str) -> str:
    r = _sh(f"git diff --stat origin/{config.DEFAULT_BRANCH}...HEAD",
            cwd=workdir)
    return r.stdout[-1500:] or "(no diff)"
