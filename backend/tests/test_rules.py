import pytest

from app.git_ops import classify_refs
from app.urls import UrlError, parse_git_target, parse_upstream, parse_webdav_remote


def test_normalize_github_and_gitee() -> None:
    github = parse_upstream("https://github.com/Octo/Hello.git")
    assert github.canonical == "https://github.com/Octo/Hello"
    assert github.platform == "github"
    assert github.dedupe_key == "https://github.com/octo/hello"
    gitee = parse_upstream("https://gitee.com/foo/bar/")
    assert gitee.canonical == "https://gitee.com/foo/bar"
    assert gitee.platform == "gitee"


def test_reject_non_https_and_foreign_host() -> None:
    with pytest.raises(UrlError):
        parse_upstream("git@github.com:foo/bar.git")
    with pytest.raises(UrlError):
        parse_upstream("https://gitlab.com/foo/bar")
    with pytest.raises(UrlError):
        parse_upstream("https://github.com/foo/bar?ref=1")


def test_target_host_must_match() -> None:
    assert parse_git_target("https://github.com/a/b", "github") == "https://github.com/a/b"
    with pytest.raises(UrlError):
        parse_git_target("https://gitee.com/a/b", "github")
    assert parse_webdav_remote("/mirrors/demo/") == "/mirrors/demo"
    with pytest.raises(UrlError):
        parse_webdav_remote("/mirrors/../secret")


def test_classify_same_behind_and_diverged() -> None:
    assert classify_refs({"refs/heads/main": "a"}, {"refs/heads/main": "a"}, lambda _a, _b: False) == "same"

    def ancestor(left: str, right: str) -> bool:
        return (left, right) == ("a", "b")

    assert classify_refs({"refs/heads/main": "a"}, {"refs/heads/main": "b"}, ancestor) == "behind"
    assert classify_refs({"refs/heads/main": "a"}, {"refs/heads/main": "c"}, lambda _a, _b: False) == "diverged"
    assert classify_refs({"refs/heads/main": "a"}, {"refs/heads/main": "a", "refs/heads/dev": "d"}, lambda _a, _b: False) == "behind"
