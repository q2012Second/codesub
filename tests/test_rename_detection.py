"""Tests for rename detection."""

import subprocess

import pytest

from codesub.detector import Detector
from codesub.git_repo import GitRepo
from codesub.models import Subscription

from .conftest import commit_changes


class TestRenameDetection:
    """Tests for file rename detection."""

    def test_rename_proposes_path_update(self, git_repo):
        """File rename should propose updating the subscription path."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)

        # Rename the file
        subprocess.run(
            ["git", "mv", "test.txt", "renamed.txt"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        commit_changes(git_repo, "Rename file")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 1

        prop = result.proposals[0]
        assert prop.old_path == "test.txt"
        assert prop.new_path == "renamed.txt"
        assert "rename" in prop.reasons

    def test_rename_preserves_line_numbers(self, git_repo):
        """Pure rename (no content changes) should preserve line numbers."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=2, end_line=4)

        # Rename without content changes
        subprocess.run(
            ["git", "mv", "test.txt", "renamed.txt"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        commit_changes(git_repo, "Rename file")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        prop = result.proposals[0]
        assert prop.old_start == prop.new_start == 2
        assert prop.old_end == prop.new_end == 4

    def test_rename_with_modification_triggers(self, git_repo):
        """Rename with modification in subscribed range should trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)

        # Rename and modify
        subprocess.run(
            ["git", "mv", "test.txt", "renamed.txt"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        renamed_file = git_repo / "renamed.txt"
        renamed_file.write_text("line 1\nMODIFIED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Rename and modify")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        # Should trigger because content changed
        assert len(result.triggers) == 1
        assert "overlap_hunk" in result.triggers[0].reasons

    def test_rename_with_shift_combines_reasons(self, git_repo):
        """Rename with line shift should include both reasons."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=4, end_line=5)

        # Rename and insert lines at top (shifting our range)
        subprocess.run(
            ["git", "mv", "test.txt", "renamed.txt"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        renamed_file = git_repo / "renamed.txt"
        renamed_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Rename and insert at top")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.proposals) == 1
        prop = result.proposals[0]
        assert "rename" in prop.reasons
        assert "line_shift" in prop.reasons
        assert prop.new_path == "renamed.txt"
        assert prop.shift == 1

    def test_rename_to_subdir(self, git_repo):
        """Rename to a subdirectory should work."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)

        # Create subdir and move file
        subdir = git_repo / "subdir"
        subdir.mkdir()
        subprocess.run(
            ["git", "mv", "test.txt", "subdir/test.txt"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        commit_changes(git_repo, "Move to subdir")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.proposals) == 1
        prop = result.proposals[0]
        assert prop.new_path == "subdir/test.txt"
