from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class GitHubIssue:
    number: int
    title: str
    body: str
    state: str
    html_url: str
    pull_request: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class GitHubReadOnlyConnector:
    """Minimal read-only GitHub connector. It never sends mutating requests."""

    def __init__(self, token: str | None = None, *, api_base: str = "https://api.github.com", fetcher: Callable[[str, dict[str, str]], Any] | None = None):
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.fetcher = fetcher or self._fetch

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "TUCH-PhiGraph-Core-v3.7"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _fetch(self, url: str, headers: dict[str, str]) -> Any:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def repository(self, owner: str, repository: str) -> dict[str, Any]:
        data = self.fetcher(f"{self.api_base}/repos/{owner}/{repository}", self._headers())
        return {"provider": "github", "owner": owner, "repository": repository, "default_branch": data.get("default_branch", "main"), "private": bool(data.get("private", False)), "html_url": data.get("html_url"), "archived": bool(data.get("archived", False))}

    def issues(self, owner: str, repository: str, *, state: str = "open", limit: int = 30) -> list[GitHubIssue]:
        query = urllib.parse.urlencode({"state": state, "per_page": min(max(limit, 1), 100)})
        rows = self.fetcher(f"{self.api_base}/repos/{owner}/{repository}/issues?{query}", self._headers())
        return [GitHubIssue(int(row["number"]), str(row.get("title", "")), str(row.get("body") or ""), str(row.get("state", "")), str(row.get("html_url", "")), "pull_request" in row) for row in rows[:limit]]

    def pull_requests(self, owner: str, repository: str, *, state: str = "open", limit: int = 30) -> list[GitHubIssue]:
        return [x for x in self.issues(owner, repository, state=state, limit=limit * 2) if x.pull_request][:limit]
