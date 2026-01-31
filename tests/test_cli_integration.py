"""Integration tests for CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import commit_changes, get_head


def run_codesub(args: list[str], cwd: Path, data_dir: Path | None = None) -> subprocess.CompletedProcess:
    """Run codesub CLI command."""
    env = None
    if data_dir:
        import os
        env = os.environ.copy()
        env["CODESUB_DATA_DIR"] = str(data_dir)

    return subprocess.run(
        [sys.executable, "-m", "codesub.cli"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def cli_data_dir(temp_dir):
    """Create a temporary data directory for CLI tests."""
    data_dir = temp_dir / "cli_data"
    data_dir.mkdir()
    return data_dir


def register_project(git_repo: Path, data_dir: Path) -> None:
    """Register a project for testing."""
    result = run_codesub(["projects", "add", str(git_repo)], git_repo, data_dir)
    assert result.returncode == 0, f"Failed to register project: {result.stderr}"


class TestCLIIntegration:
    """Integration tests for CLI commands."""

    def test_projects_add_registers_and_initializes(self, git_repo, cli_data_dir):
        """codesub projects add should register project and initialize config."""
        result = run_codesub(["projects", "add", str(git_repo)], git_repo, cli_data_dir)

        assert result.returncode == 0
        assert "Registered project" in result.stdout
        assert "Config initialized" in result.stdout

        # Config should be in data directory, not in repo
        assert not (git_repo / ".codesub").exists()
        assert (cli_data_dir / "subscriptions").exists()

    def test_projects_add_already_registered(self, git_repo, cli_data_dir):
        """codesub projects add should fail for already registered project."""
        # First registration
        run_codesub(["projects", "add", str(git_repo)], git_repo, cli_data_dir)

        # Second registration should fail
        result = run_codesub(["projects", "add", str(git_repo)], git_repo, cli_data_dir)
        assert result.returncode == 1
        assert "already registered" in result.stderr

    def test_add_subscription(self, git_repo, cli_data_dir):
        """codesub add should create a subscription."""
        register_project(git_repo, cli_data_dir)

        result = run_codesub(
            ["add", "test.txt:2-4", "--label", "Test sub", "--desc", "Test description"],
            git_repo,
            cli_data_dir,
        )

        assert result.returncode == 0
        assert "Added subscription" in result.stdout
        assert "Watching 3 line(s)" in result.stdout

    def test_add_without_registration_fails(self, git_repo, cli_data_dir):
        """codesub add without project registration should fail."""
        result = run_codesub(["add", "test.txt:2-4"], git_repo, cli_data_dir)

        assert result.returncode == 1
        assert "not registered" in result.stderr

    def test_add_invalid_location(self, git_repo, cli_data_dir):
        """codesub add with invalid location should fail."""
        register_project(git_repo, cli_data_dir)

        result = run_codesub(["add", "test.txt"], git_repo, cli_data_dir)
        assert result.returncode == 1
        assert "Invalid location" in result.stderr

    def test_add_invalid_line_range(self, git_repo, cli_data_dir):
        """codesub add with line range exceeding file should fail."""
        register_project(git_repo, cli_data_dir)

        result = run_codesub(["add", "test.txt:1-100"], git_repo, cli_data_dir)
        assert result.returncode == 1
        assert "exceeds file length" in result.stderr

    def test_list_subscriptions(self, git_repo, cli_data_dir):
        """codesub list should show subscriptions."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:2-3", "--label", "First"], git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:4-5", "--label", "Second"], git_repo, cli_data_dir)

        result = run_codesub(["list"], git_repo, cli_data_dir)

        assert result.returncode == 0
        assert "First" in result.stdout
        assert "Second" in result.stdout
        assert "Subscriptions (2)" in result.stdout

    def test_list_json(self, git_repo, cli_data_dir):
        """codesub list --json should output valid JSON."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:2-3", "--label", "Test"], git_repo, cli_data_dir)

        result = run_codesub(["list", "--json"], git_repo, cli_data_dir)

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["label"] == "Test"

    def test_list_verbose(self, git_repo, cli_data_dir):
        """codesub list --verbose should show anchors."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:2-3"], git_repo, cli_data_dir)

        result = run_codesub(["list", "--verbose"], git_repo, cli_data_dir)

        assert result.returncode == 0
        assert "Lines:" in result.stdout
        assert "line 2" in result.stdout

    def test_remove_soft(self, git_repo, cli_data_dir):
        """codesub remove should deactivate subscription."""
        register_project(git_repo, cli_data_dir)
        add_result = run_codesub(["add", "test.txt:2-3"], git_repo, cli_data_dir)

        # Extract ID from output
        for line in add_result.stdout.split("\n"):
            if "Added subscription:" in line:
                sub_id = line.split(":")[1].strip()
                break

        result = run_codesub(["remove", sub_id], git_repo, cli_data_dir)
        assert result.returncode == 0
        assert "Deactivated" in result.stdout

        # Should not appear in normal list
        list_result = run_codesub(["list"], git_repo, cli_data_dir)
        assert sub_id not in list_result.stdout

        # Should appear with --all
        list_all = run_codesub(["list", "--all"], git_repo, cli_data_dir)
        assert "inactive" in list_all.stdout

    def test_remove_hard(self, git_repo, cli_data_dir):
        """codesub remove --hard should delete subscription."""
        register_project(git_repo, cli_data_dir)
        add_result = run_codesub(["add", "test.txt:2-3"], git_repo, cli_data_dir)

        for line in add_result.stdout.split("\n"):
            if "Added subscription:" in line:
                sub_id = line.split(":")[1].strip()
                break

        result = run_codesub(["remove", "--hard", sub_id], git_repo, cli_data_dir)
        assert result.returncode == 0
        assert "Removed" in result.stdout

        # Should not appear even with --all
        list_all = run_codesub(["list", "--all"], git_repo, cli_data_dir)
        assert sub_id not in list_all.stdout

    def test_scan_detects_trigger(self, git_repo, cli_data_dir):
        """codesub scan should detect triggered subscriptions."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:2-3", "--label", "Watched"], git_repo, cli_data_dir)

        # Modify watched lines
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nMODIFIED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 2")

        result = run_codesub(["scan"], git_repo, cli_data_dir)

        assert result.returncode == 0
        assert "TRIGGERED" in result.stdout
        assert "Watched" in result.stdout

    def test_scan_fail_on_trigger(self, git_repo, cli_data_dir):
        """codesub scan --fail-on-trigger should exit with code 2."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:2-3"], git_repo, cli_data_dir)

        # Modify watched lines
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nMODIFIED\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 2")

        result = run_codesub(["scan", "--fail-on-trigger"], git_repo, cli_data_dir)
        assert result.returncode == 2

    def test_scan_proposes_shift(self, git_repo, cli_data_dir):
        """codesub scan should propose line shifts."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:4-5", "--label", "Shifted"], git_repo, cli_data_dir)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at top")

        result = run_codesub(["scan"], git_repo, cli_data_dir)

        assert result.returncode == 0
        assert "PROPOSED UPDATES" in result.stdout
        assert "Shifted" in result.stdout
        assert "line_shift" in result.stdout

    def test_scan_write_updates(self, git_repo, cli_data_dir):
        """codesub scan --write-updates should create update doc."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:4-5"], git_repo, cli_data_dir)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at top")

        update_path = git_repo / "updates.json"
        result = run_codesub(["scan", "--write-updates", str(update_path)], git_repo, cli_data_dir)

        assert result.returncode == 0
        assert update_path.exists()

        with open(update_path) as f:
            data = json.load(f)
        assert "proposals" in data
        assert len(data["proposals"]) == 1

    def test_apply_updates(self, git_repo, cli_data_dir):
        """codesub apply-updates should update subscriptions."""
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:4-5", "--label", "ToShift"], git_repo, cli_data_dir)

        # Insert at top
        test_file = git_repo / "test.txt"
        test_file.write_text("NEW\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Insert at top")

        # Scan and write updates
        update_path = git_repo / "updates.json"
        run_codesub(["scan", "--write-updates", str(update_path)], git_repo, cli_data_dir)

        # Apply updates
        result = run_codesub(["apply-updates", str(update_path)], git_repo, cli_data_dir)

        assert result.returncode == 0
        assert "Applied" in result.stdout

        # Verify subscription was updated
        list_result = run_codesub(["list", "--json"], git_repo, cli_data_dir)
        data = json.loads(list_result.stdout)
        assert data[0]["start_line"] == 5  # 4 + 1
        assert data[0]["end_line"] == 6    # 5 + 1

    def test_projects_remove_with_cleanup(self, git_repo, cli_data_dir):
        """codesub projects remove should clean up data by default."""
        # Register and add subscription
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:2-3", "--label", "Test"], git_repo, cli_data_dir)

        # Get project ID from list
        result = run_codesub(["projects", "list", "--json"], git_repo, cli_data_dir)
        projects = json.loads(result.stdout)
        project_id = projects[0]["id"]

        # Remove project
        result = run_codesub(["projects", "remove", project_id], git_repo, cli_data_dir)
        assert result.returncode == 0
        assert "Removed project" in result.stdout
        assert "data deleted" in result.stdout

        # Subscription data should be gone
        subs_dir = cli_data_dir / "subscriptions" / project_id
        assert not subs_dir.exists()

    def test_projects_remove_keep_data(self, git_repo, cli_data_dir):
        """codesub projects remove --keep-data should preserve data."""
        # Register and add subscription
        register_project(git_repo, cli_data_dir)
        run_codesub(["add", "test.txt:2-3", "--label", "Test"], git_repo, cli_data_dir)

        # Get project ID from list
        result = run_codesub(["projects", "list", "--json"], git_repo, cli_data_dir)
        projects = json.loads(result.stdout)
        project_id = projects[0]["id"]

        # Remove project with --keep-data
        result = run_codesub(["projects", "remove", "--keep-data", project_id], git_repo, cli_data_dir)
        assert result.returncode == 0
        assert "Removed project" in result.stdout
        assert "data deleted" not in result.stdout

        # Subscription data should still exist
        subs_dir = cli_data_dir / "subscriptions" / project_id
        assert subs_dir.exists()

    def test_full_workflow(self, git_repo, cli_data_dir):
        """Test complete workflow: register -> add -> modify -> scan -> apply."""
        # Register project
        result = run_codesub(["projects", "add", str(git_repo)], git_repo, cli_data_dir)
        assert result.returncode == 0

        # Add subscription
        result = run_codesub(
            ["add", "test.txt:3-4", "--label", "Important Lines"],
            git_repo,
            cli_data_dir,
        )
        assert result.returncode == 0

        # Modify file (insert at top)
        test_file = git_repo / "test.txt"
        test_file.write_text("HEADER\nline 1\nline 2\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Add header")

        # Scan
        update_path = git_repo / "updates.json"
        result = run_codesub(
            ["scan", "--write-updates", str(update_path)],
            git_repo,
            cli_data_dir,
        )
        assert result.returncode == 0
        assert "PROPOSED UPDATES" in result.stdout

        # Apply
        result = run_codesub(["apply-updates", str(update_path)], git_repo, cli_data_dir)
        assert result.returncode == 0

        # Verify final state
        list_result = run_codesub(["list", "--json"], git_repo, cli_data_dir)
        data = json.loads(list_result.stdout)
        assert len(data) == 1
        assert data[0]["start_line"] == 4
        assert data[0]["end_line"] == 5

        # Another scan should show no changes (baseline was updated to current HEAD)
        result = run_codesub(["scan"], git_repo, cli_data_dir)
        # Either shows "UNCHANGED" or "same ref" message (baseline == HEAD after apply)
        assert "UNCHANGED" in result.stdout or "same" in result.stdout
