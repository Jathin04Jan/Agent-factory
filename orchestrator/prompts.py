"""Prompt templates fed to Claude Code headless sessions."""
from . import config

GUARDRAILS = f"""
RULES — follow strictly:
- NEVER modify these paths: {', '.join(config.PROTECTED_PATHS)}
- Follow the existing code style and conventions of this repository.
- Write or update tests for any behavior you change.
- Before finishing, run the project's local checks (compile, lint, unit tests)
  and fix anything that fails. Do not finish with failing checks.
- Commit your work with clear conventional-commit messages
  (e.g. "fix(auth): handle expired session token — {{ticket}}").
- Do NOT push, do NOT open PRs, do NOT touch git remotes. The orchestrator
  handles everything beyond local commits.
"""


def build_plan_prompt(ticket: dict) -> str:
    """Architect phase: explore only, output an implementation plan. No edits."""
    return f"""You are the ARCHITECT for ticket {ticket['key']} in this repository.
Your job is to produce an implementation plan — you must NOT modify any files.

TICKET TYPE: {ticket['type']}
TITLE: {ticket['summary']}

DESCRIPTION:
{ticket['description']}

Explore the codebase (use your code-explorer subagent if available) and
produce a concrete plan containing:
1. Which files/modules must change, and how (be specific — paths and symbols).
2. New files to create, if any.
3. API/data-model contracts between frontend and backend, if both are touched.
4. What tests to add or update, and where they live.
5. Risks, side effects, and anything intentionally out of scope.

Output ONLY the plan as your final message. Do not edit, create, or commit
any files."""


def build_task_prompt(ticket: dict, plan: str | None = None) -> str:
    plan_block = (
        f"\nAn architect has already analyzed the codebase. FOLLOW THIS PLAN "
        f"(deviate only if the code contradicts it, and say so in your summary):"
        f"\n---\n{plan}\n---\n" if plan else
        "\nFirst explore the codebase to understand the relevant modules, then "
    )
    return f"""You are implementing ticket {ticket['key']} in this repository.

TICKET TYPE: {ticket['type']}
TITLE: {ticket['summary']}

DESCRIPTION:
{ticket['description']}
{plan_block}implement the {'bug fix' if ticket['type'].lower() == 'bug' else 'feature'} completely.
Use your test-writer subagent for test coverage if available.
{GUARDRAILS.replace('{ticket}', ticket['key'])}
When done, print a short summary of what you changed and why."""


def build_review_prompt(ticket: dict) -> str:
    """Reviewer phase: fresh session, read-only, adversarial."""
    return f"""You are a strict CODE REVIEWER with fresh eyes. Another engineer
implemented ticket {ticket['key']} on this branch. You must NOT modify any
files — review only.

TICKET: {ticket['summary']}
DESCRIPTION:
{ticket['description']}

Steps:
1. Run: git diff origin/{config.DEFAULT_BRANCH}...HEAD  (this is the change under review)
2. Read the surrounding code the diff touches to judge it in context.
3. Hunt for: bugs, unhandled edge cases, broken contracts between frontend
   and backend, missing/weak tests, security issues, violations of the
   ticket's requirements, and changes unrelated to the ticket.

Output format — end your final message with EXACTLY one of:
VERDICT: PASS
VERDICT: FAIL
If FAIL, precede the verdict with a numbered list of specific, actionable
findings (file + problem + what to do). Only FAIL for real problems, not
style nitpicks."""


def build_review_fix_prompt(ticket_key: str, findings: str, cycle: int) -> str:
    return f"""A code reviewer examined your implementation of ticket {ticket_key}
(review cycle {cycle} of {config.MAX_REVIEW_CYCLES}) and found these issues:

{findings}

Address every finding (or, if a finding is factually wrong, explain why in
your summary). Re-run the relevant local checks after your changes.
{GUARDRAILS.replace('{ticket}', ticket_key)}
When done, summarize what you changed for each finding."""


def build_fix_prompt(ticket_key: str, failure_logs: str, attempt: int) -> str:
    return f"""CI checks failed on the pull request for ticket {ticket_key}
(fix attempt {attempt} of {config.MAX_FIX_ATTEMPTS}).

Below are the failure logs from the CI pipeline. Diagnose the root cause,
fix it in this repository, and re-run the relevant local checks to confirm
the fix before finishing.

FAILURE LOGS:
```
{failure_logs}
```
{GUARDRAILS.replace('{ticket}', ticket_key)}
When done, print a one-paragraph summary of the root cause and your fix."""
