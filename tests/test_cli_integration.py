"""Integration tests for CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import commit_changes, get_head


def run_codesub(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run codesub CLI command."""
    return subprocess.run(
        [sys.executable, "-m", "codesub.cli"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class TestCLIIntegration:
    """Integration tests for CLI commands."""

    def test_init_creates_config(self, git_repo):
        """codesub init should create config directory and file."""
        result = run_codesub(["init"], git_repo)

        assert result.returncode == 0
        assert "Initialized" in result.stdout

        config_dir = git_repo / ".codesub"
        assert config_dir.exists()
        assert (config_dir / "subscriptions.json").exists()

    def test_init_force_overwrites(self, git_repo):
        """codesub init --force should overwrite existing config."""
        # First init
        run_codesub(["init"], git_repo)

        # Second init without force should fail
        result = run_codesub(["init"], git_repo)
        assert result.returncode == 1
        assert "already exists" in result.stderr

        # With force should succeed
        result = run_codesub(["init", "--force"], git_repo)
        assert result.returncode == 0

    def test_add_subscription(self, git_repo):
        """codesub add should create a subscription."""
        run_codesub(["init"], git_repo)

        result = run_codesub(
            ["add", "test.txt:2-4", "--label", "Test sub", "--desc", "Test description"],
            git_repo,
        )

        assert result.returncode == 0
        assert "Added subscription" in result.stdout
        assert "Watching 3 line(s)" in result.stdout

    def test_add_without_init_fails(self, git_repo):
        """codesub add without init should fail."""
        result = run_codesub(["add", "test.txt:2-4"], git_repo)

        assert result.returncode == 1
        assert "codesub init" in result.stderr  # Error message suggests running init

    def test_add_invalid_location(self, git_repo):
        """codesub add with invalid location should fail."""
        run_codesub(["init"], git_repo)

        result = run_codesub(["add", "test.txt"], git_repo)
        assert result.returncode == 1
        assert "Invalid location" in result.stderr

    def test_add_invalid_line_range(self, git_repo):
        """codesub add with line range exceeding file should fail."""
        run_codesub(["init"], git_repo)

        result = run_codesub(["add", "test.txt:1-100"], git_repo)
        assert result.returncode == 1
        assert "exceeds file length" in result.stderr

    def test_list_subscriptions(self, git_repo):
        """codesub list should show subscriptions."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:2-3", "--label", "First"], git_repo)
        run_codesub(["add", "test.txt:4-5", "--label", "Second"], git_repo)

        result = run_codesub(["list"], git_repo)

        assert result.returncode == 0
        assert "First" in result.stdout
        assert "Second" in result.stdout
        assert "Subscriptions (2)" in result.stdout

    def test_list_json(self, git_repo):
        """codesub list --json should output valid JSON."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:2-3", "--label", "Test"], git_repo)

        result = run_codesub(["list", "--json"], git_repo)

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["label"] == "Test"

    def test_list_verbose(self, git_repo):
        """codesub list --verbose should show anchors."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:2-3"], git_repo)

        result = run_codesub(["list", "--verbose"], git_repo)

        assert result.returncode == 0
        assert "Lines:" in result.stdout
        assert "line 2" in result.stdout

    def test_remove_soft(self, git_repo):
        """codesub remove should deactivate subscription."""
        run_codesub(["init"], git_repo)
        add_result = run_codesub(["add", "test.txt:2-3"], git_repo)

        # Extract ID from output
        for line in add_result.stdout.split("\n"):
            if "Added subscription:" in line:
                sub_id = line.split(":")[1].strip()
                break

        result = run_codesub(["remove", sub_id], git_repo)
        assert result.returncode == 0
        assert "Deactivated" in result.stdout

        # Should not appear in normal list
        list_result = run_codesub(["list"], git_repo)
        assert sub_id not in list_result.stdout

        # Should appear with --all
        list_all = run_codesub(["list", "--all"], git_repo)
        assert "inactive" in list_all.stdout

    def test_remove_hard(self, git_repo):
        """codesub remove --hard should delete subscription."""
        run_codesub(["init"], git_repo)
        add_result = run_codesub(["add", "test.txt:2-3"], git_repo)

        for line in add_result.stdout.split("\n"):
            if "Added subscription:" in line:
                sub_id = line.split(":")[1].strip()
                break

        result = run_codesub(["remove", "--hard", sub_id], git_repo)
        assert result.returncode == 0
        assert "Removed" in result.stdout

        # Should not appear even with --all
        list_all = run_codesub(["list", "--all"], git_repo)
        assert sub_id not in list_all.stdout

    def test_scan_detects_trigger(self, git_repo):
        """codesub scan should detect triggered subscriptions."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:2-3", "--label", "Watched"], git_repo)

        # Modify watched lines
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nMODIFIED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 2")

        result = run_codesub(["scan"], git_repo)

        assert result.returncode == 0
        assert "TRIGGERED" in result.stdout
        assert "Watched" in result.stdout

    def test_scan_fail_on_trigger(self, git_repo):
        """codesub scan --fail-on-trigger should exit with code 2."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:2-3"], git_repo)

        # Modify watched lines
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nMODIFIED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 2")

        result = run_codesub(["scan", "--fail-on-trigger"], git_repo)
        assert result.returncode == 2

    def test_scan_proposes_shift(self, git_repo):
        """codesub scan should propose line shifts."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:4-5", "--label", "Shifted"], git_repo)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at top")

        result = run_codesub(["scan"], git_repo)

        assert result.returncode == 0
        assert "PROPOSED UPDATES" in result.stdout
        assert "Shifted" in result.stdout
        assert "line_shift" in result.stdout

    def test_scan_write_updates(self, git_repo):
        """codesub scan --write-updates should create update doc."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:4-5"], git_repo)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at top")

        update_path = git_repo / "updates.json"
        result = run_codesub(["scan", "--write-updates", str(update_path)], git_repo)

        assert result.returncode == 0
        assert update_path.exists()

        with open(update_path) as f:
            data = json.load(f)
        assert "proposals" in data
        assert len(data["proposals"]) == 1

    def test_apply_updates(self, git_repo):
        """codesub apply-updates should update subscriptions."""
        run_codesub(["init"], git_repo)
        run_codesub(["add", "test.txt:4-5", "--label", "ToShift"], git_repo)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at top")

        # Scan and write updates
        update_path = git_repo / "updates.json"
        run_codesub(["scan", "--write-updates", str(update_path)], git_repo)

        # Apply updates
        result = run_codesub(["apply-updates", str(update_path)], git_repo)

        assert result.returncode == 0
        assert "Applied" in result.stdout

        # Verify subscription was updated
        list_result = run_codesub(["list", "--json"], git_repo)
        data = json.loads(list_result.stdout)
        assert data[0]["start_line"] == 5  # 4 + 1
        assert data[0]["end_line"] == 6    # 5 + 1

    def test_full_workflow(self, git_repo):
        """Test complete workflow: init -> add -> modify -> scan -> apply."""
        # Initialize
        result = run_codesub(["init"], git_repo)
        assert result.returncode == 0

        # Add subscription
        result = run_codesub(
            ["add", "test.txt:3-4", "--label", "Important Lines"],
            git_repo,
        )
        assert result.returncode == 0

        # Modify file (insert at top)
        test_file = git_repo / "test.txt"
        test_file.write_text("HEADER\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Add header")

        # Scan
        update_path = git_repo / ".codesub" / "updates.json"
        result = run_codesub(
            ["scan", "--write-updates", str(update_path)],
            git_repo,
        )
        assert result.returncode == 0
        assert "PROPOSED UPDATES" in result.stdout

        # Apply
        result = run_codesub(["apply-updates", str(update_path)], git_repo)
        assert result.returncode == 0

        # Verify final state
        list_result = run_codesub(["list", "--json"], git_repo)
        data = json.loads(list_result.stdout)
        assert len(data) == 1
        assert data[0]["start_line"] == 4
        assert data[0]["end_line"] == 5

        # Another scan should show no changes (baseline was updated to current HEAD)
        result = run_codesub(["scan"], git_repo)
        # Either shows "UNCHANGED" or "same ref" message (baseline == HEAD after apply)
        assert "UNCHANGED" in result.stdout or "same" in result.stdout
