"""Read-only public GitHub fetchers (no token required; GITHUB_TOKEN optional)."""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request

API = "https://api.github.com"


def _get(path: str, params: dict | None = None):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "openminion-triage-agent"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def _since(days: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def recent_issues(repo: str, days: int = 14, limit: int = 20) -> list[dict]:
    """Open/closed issues (not PRs) updated in the last `days` days, compacted."""
    rows = _get(f"/repos/{repo}/issues", {"state": "all", "since": _since(days), "per_page": min(limit * 2, 100), "sort": "updated"})
    out = []
    for it in rows:
        if "pull_request" in it:
            continue
        out.append({
            "number": it["number"],
            "title": it["title"],
            "state": it["state"],
            "labels": [l["name"] for l in it.get("labels", [])],
            "comments": it.get("comments", 0),
            "author": (it.get("user") or {}).get("login"),
            "body_excerpt": (it.get("body") or "")[:600],
            "url": it["html_url"],
        })
        if len(out) >= limit:
            break
    return out


def recent_pulls(repo: str, days: int = 14, limit: int = 20) -> list[dict]:
    """PRs updated in the last `days` days, with merged flag, compacted."""
    rows = _get(f"/repos/{repo}/pulls", {"state": "all", "sort": "updated", "direction": "desc", "per_page": min(limit, 100)})
    cutoff = _since(days)
    out = []
    for pr in rows:
        if pr["updated_at"] < cutoff:
            continue
        out.append({
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "merged": bool(pr.get("merged_at")),
            "merged_at": pr.get("merged_at"),
            "labels": [l["name"] for l in pr.get("labels", [])],
            "author": (pr.get("user") or {}).get("login"),
            "body_excerpt": (pr.get("body") or "")[:400],
            "url": pr["html_url"],
        })
    return out[:limit]
