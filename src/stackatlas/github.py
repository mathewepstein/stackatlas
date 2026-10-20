import httpx
from pydantic import BaseModel

from stackatlas.config import Config

API_URL = "https://api.github.com"


class RepoInfo(BaseModel):
    name: str
    full_name: str
    clone_url: str
    html_url: str
    default_branch: str
    archived: bool = False
    fork: bool = False
    pushed_at: str | None = None


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def check_owner(owner: str, token: str, client: httpx.Client | None = None) -> int:
    client = client or httpx.Client(base_url=API_URL, timeout=30)
    params = {"per_page": 1}
    response = client.get(f"/orgs/{owner}/repos", params=params, headers=_headers(token))
    if response.status_code == 404:
        response = client.get(f"/users/{owner}/repos", params=params, headers=_headers(token))
    response.raise_for_status()
    last = response.links.get("last", {}).get("url")
    if last:
        return int(httpx.URL(last).params.get("page", "1"))
    return len(response.json())


def list_repos(owner: str, token: str, client: httpx.Client | None = None) -> list[RepoInfo]:
    client = client or httpx.Client(base_url=API_URL, timeout=30)
    headers = _headers(token)
    first = client.get(f"/orgs/{owner}/repos", params={"per_page": 100}, headers=headers)
    if first.status_code == 404:
        first = client.get(f"/users/{owner}/repos", params={"per_page": 100}, headers=headers)
    first.raise_for_status()

    repos: list[RepoInfo] = []
    response = first
    while True:
        repos.extend(RepoInfo.model_validate(r) for r in response.json())
        next_url = response.links.get("next", {}).get("url")
        if not next_url:
            return repos
        response = client.get(next_url, headers=headers)
        response.raise_for_status()


def filter_repos(repos: list[RepoInfo], config: Config) -> list[RepoInfo]:
    return [
        r
        for r in repos
        if not (config.skip_archived and r.archived)
        and not (config.skip_forks and r.fork)
        and config.includes(r.name)
    ]
