"""Agent Factory orchestrator — polls Jira, runs Claude Code, gates on Slack,
self-heals CI, merges. One ticket at a time. Restart-safe (state lives in Jira).

Run:  python -m orchestrator.main
"""
import logging
import time

from . import agent_runner, config, github_ops, jira_client, prompts, sandbox
from . import slack_client as slack
from . import slack_trigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-8s %(levelname)-7s %(message)s",
)
log = logging.getLogger("factory")
USING_JIRA = config.TRIGGER == "jira"


def escalate(ticket_key: str, thread: str, reason: str) -> None:
    slack.post(f":rotating_light: *{ticket_key}* needs a human: {reason}", thread)
    if USING_JIRA:
        jira_client.comment(ticket_key, f"Agent factory escalation: {reason}")


def process_ticket(ticket: dict) -> None:
    key = ticket["key"]
    log.info("=== Processing %s: %s ===", key, ticket["summary"])
    if USING_JIRA:
        jira_client.transition(key, config.JIRA_STATUS_IN_PROGRESS)
    thread = slack.post(
        f":robot_face: Picked up *{key}* — _{ticket['summary']}_\n"
        f"Working on a {ticket['type'].lower()} now…"
    )

    # 1. Fresh workspace
    workdir, branch = sandbox.prepare_workspace(key)
    phased = ticket["type"].lower() in config.PHASED_TYPES

    # 1a. Architect phase (features only): plan before touching code
    plan = None
    if phased:
        slack.post(":triangular_ruler: Architect phase — analyzing the "
                   "codebase and drafting a plan…", thread)
        ok, plan = agent_runner.run_claude(prompts.build_plan_prompt(ticket),
                                           workdir)
        if not ok:
            escalate(key, thread, f"planning session failed. {plan[:500]}")
            return
        slack.post(f":clipboard: Plan ready:\n```{plan[:2500]}```", thread)

    # 1b. Implement phase
    ok, result = agent_runner.run_claude(
        prompts.build_task_prompt(ticket, plan), workdir)
    if not ok or not sandbox.has_commits(workdir):
        escalate(key, thread, f"coding session produced no usable commits. {result[:500]}")
        return

    # 1c. Review phase (features only): fresh adversarial session
    review_note = ""
    if phased:
        for cycle in range(1, config.MAX_REVIEW_CYCLES + 1):
            slack.post(f":mag: Review phase — fresh-eyes pass "
                       f"{cycle}/{config.MAX_REVIEW_CYCLES}…", thread)
            ok, review = agent_runner.run_claude(
                prompts.build_review_prompt(ticket), workdir)
            if not ok:
                review_note = "\n:warning: review session errored — unreviewed."
                break
            if "VERDICT: PASS" in review:
                review_note = "\n:white_check_mark: passed independent code review."
                break
            findings = review.split("VERDICT:")[0].strip()
            slack.post(f":mag: Review found issues, sending back to "
                       f"implementer:\n```{findings[:1500]}```", thread)
            ok, _ = agent_runner.run_claude(
                prompts.build_review_fix_prompt(key, findings, cycle), workdir)
            if not ok:
                review_note = "\n:warning: review-fix session errored."
                break
        else:
            review_note = (f"\n:warning: reviewer still unsatisfied after "
                           f"{config.MAX_REVIEW_CYCLES} cycles — check the "
                           f"findings above before approving.")

    # 2. Guardrails: protected paths + optional local verification
    touched = sandbox.touched_protected_paths(workdir)
    if touched:
        escalate(key, thread, f"agent modified protected paths: {touched}")
        return
    verified, vlog = sandbox.run_verify(workdir)
    if not verified:
        escalate(key, thread, f"local verification failed:\n```{vlog[-800:]}```")
        return

    # 3. Sandbox preview + Slack approval gate
    preview_ok = sandbox.up(workdir)
    slack.post(
        f"*{key}* is ready for testing :test_tube:\n"
        + (f"Preview: {config.SANDBOX_URL}\n" if preview_ok
           else ":warning: sandbox failed to start — review the diff instead\n")
        + f"```{sandbox.diff_summary(workdir)}```\n"
        f"Agent summary: {result[:1000]}{review_note}\n\n"
        f"Reply *approve* in this thread to push → PR → CI → merge, "
        f"or *reject* to stop.",
        thread,
    )
    decision = slack.wait_for_approval(thread)
    sandbox.down(workdir)
    if decision != "approved":
        escalate(key, thread, f"preview was {decision} — nothing pushed.")
        return

    # 4. Push + PR
    github_ops.push_branch(workdir, branch)
    pr_url = github_ops.create_pr(
        workdir, branch,
        title=f"{key}: {ticket['summary']}",
        body=f"Automated implementation of {key} by the agent factory.\n\n"
             f"Approved via Slack preview before push.",
    )
    slack.post(f":arrow_up: Pushed and opened PR: {pr_url}\nWatching CI…", thread)

    # 5. CI watch + self-heal loop (every fix gets re-checked by CI)
    attempt = 0
    while True:
        status = github_ops.wait_for_checks(branch)
        if status == "success":
            break
        if status == "timeout":
            escalate(key, thread, "CI did not settle in time.")
            return
        attempt += 1
        if attempt > config.MAX_FIX_ATTEMPTS:
            escalate(key, thread,
                     f"CI still failing after {config.MAX_FIX_ATTEMPTS} fix "
                     f"attempts. PR left open: {pr_url}")
            return
        logs = github_ops.failed_check_logs(branch)
        slack.post(f":wrench: CI failed — fix attempt {attempt}/"
                   f"{config.MAX_FIX_ATTEMPTS}…", thread)
        ok, _ = agent_runner.run_claude(
            prompts.build_fix_prompt(key, logs, attempt), workdir)
        if not ok:
            escalate(key, thread, "fix session errored out.")
            return
        github_ops.push_branch(workdir, branch)

    # 6. Merge → existing CI/CD takes over
    if config.AUTO_MERGE:
        if github_ops.merge_pr(branch):
            if USING_JIRA:
                jira_client.transition(key, config.JIRA_STATUS_DONE)
                jira_client.comment(key, f"Merged automatically: {pr_url}")
            slack.post(f":white_check_mark: *{key}* merged to "
                       f"`{config.DEFAULT_BRANCH}` — deployment pipeline is "
                       f"taking it from here.", thread)
        else:
            escalate(key, thread, f"CI is green but merge failed. PR: {pr_url}")
    else:
        slack.post(f":white_check_mark: *{key}* is green and ready — "
                   f"merge manually: {pr_url}", thread)


def fetch_tickets() -> list[dict]:
    if USING_JIRA:
        return jira_client.fetch_ready_tickets()
    return slack_trigger.fetch_new_tasks()


def main() -> None:
    log.info("Agent factory started. Trigger=%s, polling every %ss",
             config.TRIGGER, config.JIRA_POLL_SECONDS)
    while True:
        try:
            for ticket in fetch_tickets():
                try:
                    process_ticket(ticket)
                except Exception:
                    log.exception("Ticket %s crashed", ticket["key"])
                    slack.post(f":boom: Unhandled error on *{ticket['key']}* — "
                               f"check orchestrator logs.")
        except Exception:
            log.exception("Poll cycle failed")
        time.sleep(config.JIRA_POLL_SECONDS)


if __name__ == "__main__":
    main()
