import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any
from retry import backoff_retry, TransientError

# load environment variables
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_BASE = os.getenv("GITHUB_API_BASE", "https://api.github.com")

session = requests.Session()
if GITHUB_TOKEN:
    session.headers.update({
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    })


def _handle_resp(resp: requests.Response) -> Dict[str, Any]:
    """Helper to classify GitHub responses as transient/fatal."""
    if resp.status_code in (429, 500, 502, 503, 504):
        raise TransientError(f"GitHub transient {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400:
        raise Exception(f"GitHub error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def github_create_issue(owner: str, repo: str, title: str, body: str = "", dry_run: bool = False) -> Dict[str, Any]:
    """
    Create a GitHub issue.
    Returns issue number + url.
    Respects dry_run and retries on transient errors.
    """
    payload = {"title": title, "body": body}

    if dry_run:
        return {"dry_run": True, "owner": owner, "repo": repo, **payload}

    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"

    def attempt():
        resp = session.post(url, json=payload, timeout=20)
        data = _handle_resp(resp)
        return {"number": data.get("number"), "url": data.get("html_url")}

    return backoff_retry(attempt, max_attempts=4, base=0.6, factor=2.0, jitter=0.3)


def echo(message: str, dry_run: bool = False) -> Dict[str, Any]:
    payload = {"message": message}
    if dry_run:
        return {"ok": True, "dry_run": True, **payload}
    return {"ok": True, **payload}

TOOL_REGISTRY = {
    "echo": echo,
    "github.create_issue": github_create_issue,
}