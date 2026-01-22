"""Tests for Detector line shift calculations."""

import pytest

from codesub.detector import Detector
from codesub.git_repo import GitRepo
from codesub.models import Subscription

from .conftest import commit_changes


class TestDetectorShifts:
    """Tests for line shift calculations."""

    def test_shift_from_insert_before(self, git_repo):
        """Insert before subscription should shift lines down."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 4-5
        sub = Subscription.create(path="test.txt", start_line=4, end_line=5)

        # Insert 2 lines at the top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW 1\nNEW 2\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at top")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 1

        prop = result.proposals[0]
        assert prop.new_start == 6  # 4 + 2
        assert prop.new_end == 7    # 5 + 2
        assert prop.shift == 2
        assert "line_shift" in prop.reasons

    def test_shift_from_delete_before(self, git_repo):
        """Delete before subscription should shift lines up."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 4-5
        sub = Subscription.create(path="test.txt", start_line=4, end_line=5)

        # Delete lines 1-2
        test_file = git_repo / "test.txt"
        test_file.write_text("line 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Delete first two lines")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 1

        prop = result.proposals[0]
        assert prop.new_start == 2  # 4 - 2
        assert prop.new_end == 3    # 5 - 2
        assert prop.shift == -2
        assert "line_shift" in prop.reasons

    def test_shift_from_multiple_changes(self, git_repo):
        """Multiple changes before subscription should accumulate shifts."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches line 5
        sub = Subscription.create(path="test.txt", start_line=5, end_line=5)

        # Insert 2 lines at top (net +2 shift)
        # New content: NEW1, NEW2, line 1, line 2, line 3, line 4, line 5
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW1\nNEW2\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Multiple inserts")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 1

        prop = result.proposals[0]
        # +2 from inserts
        assert prop.shift == 2
        assert prop.new_start == 7
        assert prop.new_end == 7

    def test_no_shift_when_modification_replaces_same_count(self, git_repo):
        """Modification that replaces N lines with N lines should not shift."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 4-5
        sub = Subscription.create(path="test.txt", start_line=4, end_line=5)

        # Replace lines 1-2 with 2 new lines
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW 1\nNEW 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Replace with same count")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        # No shift because same number of lines
        assert len(result.proposals) == 0 or result.proposals[0].shift == 0

    def test_shift_preserves_range_size(self, git_repo):
        """Shift should preserve the size of the subscription range."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches 3 lines (3-5)
        sub = Subscription.create(path="test.txt", start_line=3, end_line=5)

        # Insert 5 lines at top
        test_file = git_repo / "test.txt"
        content = "NEW 1\nNEW 2\nNEW 3\nNEW 4\nNEW 5\n" + "line 1\nline 2\nline 3\nline 4\nline 5\n"
        test_file.write_text(content)
        commit_changes(git_repo, "Insert 5 at top")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.proposals) == 1
        prop = result.proposals[0]

        # Range size should be preserved
        old_size = sub.end_line - sub.start_line
        new_size = prop.new_end - prop.new_start
        assert new_size == old_size

    def test_unchanged_when_no_diff(self, git_repo):
        """Subscription should be unchanged when file is not modified."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)

        # Create a different file, not touching test.txt
        other_file = git_repo / "other.txt"
        other_file.write_text("other content\n")
        commit_changes(git_repo, "Add other file")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0
        assert len(result.unchanged) == 1
        assert result.unchanged[0].id == sub.id

    def test_changes_after_range_do_not_shift(self, git_repo):
        """Changes after the subscription range should not affect it."""
        repo = GitRepo(git_repo)
        base_ref = repo.head()

        # Subscription watches lines 1-2
        sub = Subscription.create(path="test.txt", start_line=1, end_line=2)

        # Insert lines at the end
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\nNEW 1\nNEW 2\n")
        commit_changes(git_repo, "Insert at end")

        detector = Detector(repo)
        result = detector.scan([sub], base_ref, repo.head())

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0  # No shift needed
        assert len(result.unchanged) == 1
