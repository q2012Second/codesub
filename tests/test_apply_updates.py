"""Tests for applying updates."""

import json

import pytest

from codesub.config_store import ConfigStore
from codesub.git_repo import GitRepo
from codesub.models import Anchor, Subscription
from codesub.updater import Updater

from .conftest import commit_changes


class TestApplyUpdates:
    """Tests for the Updater class."""

    def test_apply_shift_updates_lines(self, git_repo):
        """Apply shift should update start and end lines."""
        repo = GitRepo(git_repo)
        store = ConfigStore(git_repo)
        base_ref = repo.head()

        # Initialize and add subscription
        store.init(base_ref)
        sub = Subscription.create(path="test.txt", start_line=3, end_line=4)
        store.add_subscription(sub)

        # Create changes
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        target_ref = commit_changes(git_repo, "Insert at top")

        # Create update document
        update_data = {
            "schema_version": 1,
            "base_ref": base_ref,
            "target_ref": target_ref,
            "triggers": [],
            "proposals": [
                {
                    "subscription_id": sub.id,
                    "old_path": "test.txt",
                    "old_start": 3,
                    "old_end": 4,
                    "new_path": "test.txt",
                    "new_start": 4,
                    "new_end": 5,
                    "reasons": ["line_shift"],
                    "shift": 1,
                }
            ],
        }

        updater = Updater(store, repo)
        applied, warnings = updater.apply(update_data)

        assert len(applied) == 1
        assert applied[0] == sub.id
        assert len(warnings) == 0

        # Verify subscription was updated
        updated_sub = store.get_subscription(sub.id[:8])
        assert updated_sub.start_line == 4
        assert updated_sub.end_line == 5

    def test_apply_rename_updates_path(self, git_repo):
        """Apply rename should update the path."""
        import subprocess

        repo = GitRepo(git_repo)
        store = ConfigStore(git_repo)
        base_ref = repo.head()

        # Initialize and add subscription
        store.init(base_ref)
        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)
        store.add_subscription(sub)

        # Rename file
        subprocess.run(
            ["git", "mv", "test.txt", "renamed.txt"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        target_ref = commit_changes(git_repo, "Rename file")

        # Create update document
        update_data = {
            "schema_version": 1,
            "base_ref": base_ref,
            "target_ref": target_ref,
            "triggers": [],
            "proposals": [
                {
                    "subscription_id": sub.id,
                    "old_path": "test.txt",
                    "old_start": 2,
                    "old_end": 3,
                    "new_path": "renamed.txt",
                    "new_start": 2,
                    "new_end": 3,
                    "reasons": ["rename"],
                    "shift": None,
                }
            ],
        }

        updater = Updater(store, repo)
        applied, warnings = updater.apply(update_data)

        assert len(applied) == 1

        updated_sub = store.get_subscription(sub.id[:8])
        assert updated_sub.path == "renamed.txt"

    def test_apply_updates_baseline(self, git_repo):
        """Apply should update the baseline ref."""
        repo = GitRepo(git_repo)
        store = ConfigStore(git_repo)
        base_ref = repo.head()

        store.init(base_ref)
        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)
        store.add_subscription(sub)

        # Make a change
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        target_ref = commit_changes(git_repo, "Insert at top")

        update_data = {
            "base_ref": base_ref,
            "target_ref": target_ref,
            "proposals": [
                {
                    "subscription_id": sub.id,
                    "new_path": "test.txt",
                    "new_start": 3,
                    "new_end": 4,
                }
            ],
        }

        updater = Updater(store, repo)
        updater.apply(update_data)

        assert store.get_baseline() == target_ref

    def test_apply_re_snapshots_anchors(self, git_repo):
        """Apply should re-snapshot anchors from target ref."""
        repo = GitRepo(git_repo)
        store = ConfigStore(git_repo)
        base_ref = repo.head()

        store.init(base_ref)
        sub = Subscription.create(
            path="test.txt",
            start_line=2,
            end_line=3,
            anchors=Anchor(
                context_before=["line 1"],
                lines=["line 2", "line 3"],
                context_after=["line 4"],
            ),
        )
        store.add_subscription(sub)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        target_ref = commit_changes(git_repo, "Insert at top")

        update_data = {
            "base_ref": base_ref,
            "target_ref": target_ref,
            "proposals": [
                {
                    "subscription_id": sub.id,
                    "new_path": "test.txt",
                    "new_start": 3,  # shifted by 1
                    "new_end": 4,
                }
            ],
        }

        updater = Updater(store, repo)
        updater.apply(update_data)

        updated_sub = store.get_subscription(sub.id[:8])
        # Anchors should reflect new position
        assert updated_sub.anchors.lines == ["line 2", "line 3"]
        # Context should include the new first line
        assert "NEW" in updated_sub.anchors.context_before or "line 1" in updated_sub.anchors.context_before

    def test_dry_run_does_not_modify(self, git_repo):
        """Dry run should not modify config."""
        repo = GitRepo(git_repo)
        store = ConfigStore(git_repo)
        base_ref = repo.head()

        store.init(base_ref)
        sub = Subscription.create(path="test.txt", start_line=2, end_line=3)
        store.add_subscription(sub)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        target_ref = commit_changes(git_repo, "Insert at top")

        update_data = {
            "base_ref": base_ref,
            "target_ref": target_ref,
            "proposals": [
                {
                    "subscription_id": sub.id,
                    "new_path": "test.txt",
                    "new_start": 3,
                    "new_end": 4,
                }
            ],
        }

        updater = Updater(store, repo)
        applied, warnings = updater.apply(update_data, dry_run=True)

        assert len(applied) == 1

        # Subscription should not be modified
        unchanged_sub = store.get_subscription(sub.id[:8])
        assert unchanged_sub.start_line == 2
        assert unchanged_sub.end_line == 3

        # Baseline should not be modified
        assert store.get_baseline() == base_ref

    def test_warning_for_missing_subscription(self, git_repo):
        """Should warn when subscription ID not found."""
        repo = GitRepo(git_repo)
        store = ConfigStore(git_repo)
        base_ref = repo.head()

        store.init(base_ref)

        update_data = {
            "base_ref": base_ref,
            "target_ref": base_ref,
            "proposals": [
                {
                    "subscription_id": "nonexistent-id",
                    "new_path": "test.txt",
                    "new_start": 2,
                    "new_end": 3,
                }
            ],
        }

        updater = Updater(store, repo)
        applied, warnings = updater.apply(update_data)

        assert len(applied) == 0
        assert len(warnings) == 1
        assert "not found" in warnings[0]

    def test_warning_for_content_mismatch(self, git_repo):
        """Should warn when content at new location differs significantly."""
        repo = GitRepo(git_repo)
        store = ConfigStore(git_repo)
        base_ref = repo.head()

        store.init(base_ref)
        sub = Subscription.create(
            path="test.txt",
            start_line=2,
            end_line=3,
            anchors=Anchor(
                context_before=["line 1"],
                lines=["line 2", "line 3"],
                context_after=["line 4"],
            ),
        )
        store.add_subscription(sub)

        # Completely change the content
        test_file = git_repo / "test.txt"
        test_file.write_text("alpha\nbeta\ngamma\ndelta\nepsilon\n")
        target_ref = commit_changes(git_repo, "Complete change")

        update_data = {
            "base_ref": base_ref,
            "target_ref": target_ref,
            "proposals": [
                {
                    "subscription_id": sub.id,
                    "new_path": "test.txt",
                    "new_start": 2,
                    "new_end": 3,
                }
            ],
        }

        updater = Updater(store, repo)
        applied, warnings = updater.apply(update_data)

        # Should still apply but with warning
        assert len(applied) == 1
        assert any("differs significantly" in w for w in warnings)
