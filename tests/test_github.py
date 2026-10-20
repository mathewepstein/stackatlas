import httpx
import pytest

from stackatlas.config import Config
from stackatlas.github import RepoInfo, check_owner, filter_repos, list_repos

NEXT_PAGE = "https://api.github.com/orgs/acme/repos?per_page=100&page=2"


def _repo(name, **kw):
    return {
        "name": name,
        "full_name": f"acme/{name}",
        "clone_url": f"https://github.com/acme/{name}.git",
        "html_url": f"https://github.com/acme/{name}",
        "default_branch": "main",
        "archived": False,
        "fork": False,
        "pushed_at": "2026-01-01T00:00:00Z",
        **kw,
    }


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")


def test_list_repos_follows_pagination_and_sends_token():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[_repo("b")])
        return httpx.Response(
            200,
            json=[_repo("a")],
            headers={"Link": f'<{NEXT_PAGE}>; rel="next"'},
        )

    repos = list_repos("acme", "tok", client=_client(handler))
    assert [r.name for r in repos] == ["a", "b"]
    assert all(r.headers["Authorization"] == "Bearer tok" for r in seen)
    assert seen[0].url.path == "/orgs/acme/repos"


def test_list_repos_falls_back_to_user_account():
    def handler(request):
        if request.url.path.startswith("/orgs/"):
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=[_repo("solo")])

    repos = list_repos("someone", "tok", client=_client(handler))
    assert [r.name for r in repos] == ["solo"]


def test_list_repos_raises_on_auth_failure():
    def handler(request):
        return httpx.Response(401, json={"message": "Bad credentials"})

    with pytest.raises(httpx.HTTPStatusError):
        list_repos("acme", "bad", client=_client(handler))


def test_check_owner_counts_visible_repos_for_org_or_user():
    last = "https://api.github.com/organizations/1/repos?per_page=1&page=82"

    def handler(request):
        assert request.url.params["per_page"] == "1"
        if request.url.path == "/orgs/acme/repos":
            link = f'<{NEXT_PAGE}>; rel="next", <{last}>; rel="last"'
            return httpx.Response(200, json=[_repo("a")], headers={"Link": link})
        if request.url.path == "/orgs/someone/repos":
            return httpx.Response(404, json={})
        return httpx.Response(200, json=[_repo("solo")])

    assert check_owner("acme", "tok", client=_client(handler)) == 82
    assert check_owner("someone", "tok", client=_client(handler)) == 1


def test_check_owner_raises_when_missing():
    with pytest.raises(httpx.HTTPStatusError):
        check_owner("x", "tok", client=_client(lambda r: httpx.Response(404, json={})))


def test_filter_repos_drops_archived_forks_and_excluded():
    repos = [
        RepoInfo.model_validate(_repo("keep")),
        RepoInfo.model_validate(_repo("old", archived=True)),
        RepoInfo.model_validate(_repo("forked", fork=True)),
        RepoInfo.model_validate(_repo("x-sandbox")),
    ]
    kept = filter_repos(repos, Config(exclude=["*-sandbox"]))
    assert [r.name for r in kept] == ["keep"]
