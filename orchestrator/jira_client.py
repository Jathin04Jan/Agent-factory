"""Minimal Jira Cloud REST client (outbound polling — no webhooks needed)."""
import logging

import requests

from . import config

log = logging.getLogger("jira")
AUTH = (config.JIRA_EMAIL, config.JIRA_API_TOKEN)
API = f"{config.JIRA_BASE_URL}/rest/api/2"


def fetch_ready_tickets() -> list[dict]:
    """Return tickets matching JIRA_JQL as [{key, summary, description, type}]."""
    r = requests.get(
        f"{API}/search",
        params={"jql": config.JIRA_JQL, "maxResults": 10,
                "fields": "summary,description,issuetype"},
        auth=AUTH, timeout=30,
    )
    r.raise_for_status()
    out = []
    for issue in r.json().get("issues", []):
        f = issue["fields"]
        out.append({
            "key": issue["key"],
            "summary": f.get("summary") or "",
            "description": f.get("description") or "",
            "type": (f.get("issuetype") or {}).get("name", "Task"),
        })
    return out


def transition(key: str, status_name: str) -> None:
    """Move a ticket to the named status (looks up the transition id)."""
    r = requests.get(f"{API}/issue/{key}/transitions", auth=AUTH, timeout=30)
    r.raise_for_status()
    for t in r.json().get("transitions", []):
        if t["to"]["name"].lower() == status_name.lower():
            requests.post(
                f"{API}/issue/{key}/transitions",
                json={"transition": {"id": t["id"]}}, auth=AUTH, timeout=30,
            ).raise_for_status()
            return
    log.warning("No transition to '%s' found for %s", status_name, key)


def comment(key: str, body: str) -> None:
    requests.post(
        f"{API}/issue/{key}/comment", json={"body": body}, auth=AUTH, timeout=30
    ).raise_for_status()
