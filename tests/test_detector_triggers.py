"""Tests for Detector trigger detection."""

import pytest

from codesub.detector import Detector
from codesub.git_repo import GitRepo
from codesub.models import Subscription

from .conftest import commit_changes, get_head


class TestDetectorTriggers:
    """Tests for trigger detection."""

    def test_trigger_on_overlapping_modification(self, git_repo):
        """When a hunk modifies lines that overlap with subscription, trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 2-3
        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)

        # Modify line 2
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nMODIFIED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 2")
        target_ref = repo.head()

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].subscription_id == sub.id
        assert "overlap_hunk" in result.triggers[0].reasons

    def test_trigger_on_deletion_in_range(self, git_repo):
        """When lines in the subscription range are deleted, trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 2-4
        sub = Subscription.create(path="test.txt", start_line=2, end_line=4)

        # Delete lines 2-3
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nline 4\nline 5\n")
        commit_changes(git_repo, "Delete lines 2-3")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 1
        assert "overlap_hunk" in result.triggers[0].reasons

    def test_trigger_on_insert_inside_range(self, git_repo):
        """When lines are inserted inside the subscription range, trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 2-4
        sub = Subscription.create(path="test.txt", start_line=2, end_line=4)

        # Insert a line between line 2 and line 3
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nline 2\nINSERTED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert line between 2 and 3")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 1
        assert "insert_inside_range" in result.triggers[0].reasons

    def test_trigger_on_file_deleted(self, git_repo):
        """When the subscribed file is deleted, trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)

        # Delete the file
        import subprocess
        subprocess.run(["git", "rm", "test.txt"], cwd=git_repo, capture_output=True, check=True)
        commit_changes(git_repo, "Delete file")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 1
        assert "file_deleted" in result.triggers[0].reasons

    def test_no_trigger_modification_before_range(self, git_repo):
        """Modification before subscription range should not trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 4-5
        sub = Subscription.create(path="test.txt", start_line=4, end_line=5)

        # Modify line 1
        test_file = git_repo / "test.txt"
        test_file.write_text("MODIFIED\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 1")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        # Should have a shift proposal instead
        assert len(result.proposals) == 0  # Same position, no shift needed

    def test_no_trigger_modification_after_range(self, git_repo):
        """Modification after subscription range should not trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 1-2
        sub = Subscription.create(path="test.txt", start_line=1, end_line=2)

        # Modify line 5
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\nMODIFIED\n")
        commit_changes(git_repo, "Modify line 5")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0  # No shift needed

    def test_no_trigger_insert_before_range(self, git_repo):
        """Insert before subscription range should shift but not trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 3-4
        sub = Subscription.create(path="test.txt", start_line=3, end_line=4)

        # Insert at the beginning
        test_file = git_repo / "test.txt"
        test_file.write_text("INSERTED\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at beginning")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 1
        assert result.proposals[0].shift == 1

    def test_boundary_insert_after_last_line_no_trigger(self, git_repo):
        """Insert after the last subscribed line should not trigger."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 2-3
        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)

        # Insert after line 3 (between 3 and 4)
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nINSERTED\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert after line 3")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        # Insert after old_start=3, sub range is 2-3
        # Condition: sub_start <= hunk.old_start < sub_end
        # 2 <= 3 < 3 => False, so no trigger
        assert len(result.triggers) == 0

    def test_inactive_subscriptions_ignored(self, git_repo):
        """Inactive subscriptions should not be scanned."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)
        sub.active = False

        # Modify line 2
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nMODIFIED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 2")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0
        assert len(result.unchanged) == 0
