"""Tests for bundle artifact version calculation."""

import subprocess
from pathlib import Path

import pytest

VERSION_SCRIPT = Path(__file__).parent.parent / "scripts" / "bundle-version.bash"


def git(repo: Path, *args: str) -> str:
    """Run Git in a temporary repository and return stdout."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def bundle_version(repo: Path) -> str:
    """Calculate the bundle version for a repository."""
    return subprocess.run(  # noqa: S603
        ["bash", str(VERSION_SCRIPT), str(repo)],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """Create a repository with one committed file."""
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "user.name", "Test User")
    git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "file.txt").write_text("initial\n")
    git(tmp_path, "add", "file.txt")
    git(tmp_path, "commit", "--quiet", "-m", "initial")
    return tmp_path


def test_clean_release_tag_uses_release_version(repo):
    git(repo, "tag", "v0.4.0")

    assert bundle_version(repo) == "0.4.0"


def test_commit_after_release_includes_commit_id(repo):
    git(repo, "tag", "v0.4.0")
    (repo / "file.txt").write_text("changed\n")
    git(repo, "commit", "--quiet", "-am", "change")

    assert bundle_version(repo) == f"0.4.0-g{git(repo, 'rev-parse', '--short', 'HEAD')}"


@pytest.mark.parametrize("untracked", [False, True])
def test_dirty_release_checkout_includes_commit_id(repo, untracked):
    git(repo, "tag", "v0.4.0")
    if untracked:
        (repo / "new-file.txt").write_text("new\n")
    else:
        (repo / "file.txt").write_text("changed\n")

    assert bundle_version(repo) == f"0.4.0-g{git(repo, 'rev-parse', '--short', 'HEAD')}"


def test_non_version_tags_are_ignored(repo):
    git(repo, "tag", "v0.4.0")
    (repo / "file.txt").write_text("changed\n")
    git(repo, "commit", "--quiet", "-am", "change")
    git(repo, "tag", "nightly")

    assert bundle_version(repo) == f"0.4.0-g{git(repo, 'rev-parse', '--short', 'HEAD')}"


def test_repository_without_version_tags_uses_zero_version(repo):
    assert bundle_version(repo) == f"0.0.0-g{git(repo, 'rev-parse', '--short', 'HEAD')}"
