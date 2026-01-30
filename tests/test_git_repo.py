"""Tests for GitRepo wrapper."""

import subprocess

import pytest

from codesub.errors import FileNotFoundAtRefError, NotAGitRepoError
from codesub.git_repo import GitRepo

from .conftest import commit_changes, get_head


class TestGitRepo:
    """Tests for GitRepo class."""

    def test_root_finds_repo(self, git_repo):
        repo = GitRepo(git_repo)
        # Resolve symlinks for comparison (macOS /var -> /private/var)
        assert repo.root.resolve() == git_repo.resolve()

    def test_root_from_subdir(self, git_repo):
        subdir = git_repo / "subdir"
        subdir.mkdir()

        repo = GitRepo(subdir)
        # Resolve symlinks for comparison
        assert repo.root.resolve() == git_repo.resolve()

    def test_not_a_repo_raises(self, temp_dir):
        with pytest.raises(NotAGitRepoError):
            repo = GitRepo(temp_dir)
            _ = repo.root

    def test_head_returns_commit_hash(self, git_repo):
        repo = GitRepo(git_repo)
        head = repo.head()

        assert len(head) == 40
        assert all(c in "0123456789abcdef" for c in head)

    def test_resolve_ref_head(self, git_repo):
        repo = GitRepo(git_repo)
        resolved = repo.resolve_ref("HEAD")

        assert len(resolved) == 40

    def test_show_file_returns_lines(self, git_repo):
        repo = GitRepo(git_repo)
        lines = repo.show_file("HEAD", "test.txt")

        assert lines == ["line 1", "line 2", "line 3", "line 4", "line 5"]

    def test_show_file_not_found_raises(self, git_repo):
        repo = GitRepo(git_repo)

        with pytest.raises(FileNotFoundAtRefError) as exc_info:
            repo.show_file("HEAD", "nonexistent.txt")

        assert exc_info.value.path == "nonexistent.txt"

    def test_show_file_at_older_commit(self, git_repo):
        repo = GitRepo(git_repo)
        old_head = repo.head()

        # Modify the file
        test_file = git_repo / "test.txt"
        test_file.write_text("modified content\n")
        commit_changes(git_repo, "Modify file")

        # Old commit should have old content
        old_lines = repo.show_file(old_head, "test.txt")
        assert old_lines == ["line 1", "line 2", "line 3", "line 4", "line 5"]

        # New commit should have new content
        new_lines = repo.show_file("HEAD", "test.txt")
        assert new_lines == ["modified content"]

    def test_diff_patch_returns_diff(self, git_repo):
        repo = GitRepo(git_repo)
        old_head = repo.head()

        # Modify the file
        test_file = git_repo / "test.txt"
        test_file.write_text("line 1\nmodified\nline 3\nline 4\nline 5\n")
        commit_changes(git_repo, "Modify line 2")

        diff = repo.diff_patch(old_head, "HEAD")

        assert "test.txt" in diff
        assert "@@" in diff

    def test_diff_patch_empty_for_same_ref(self, git_repo):
        repo = GitRepo(git_repo)
        head = repo.head()

        diff = repo.diff_patch(head, head)
        assert diff.strip() == ""

    def test_diff_name_status_detects_rename(self, git_repo):
        repo = GitRepo(git_repo)
        old_head = repo.head()

        # Rename the file
        subprocess.run(
            ["git", "mv", "test.txt", "renamed.txt"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        commit_changes(git_repo, "Rename file")

        name_status = repo.diff_name_status(old_head, "HEAD")
        assert "R" in name_status
        assert "test.txt" in name_status
        assert "renamed.txt" in name_status

    def test_relative_path(self, git_repo):
        repo = GitRepo(git_repo)
        abs_path = git_repo / "subdir" / "file.txt"

        rel = repo.relative_path(abs_path)
        assert rel == "subdir/file.txt"

    def test_list_files_at_head(self, git_repo):
        repo = GitRepo(git_repo)
        files = repo.list_files("HEAD")

        assert isinstance(files, list)
        assert "test.txt" in files

    def test_list_files_multiple_files(self, git_repo):
        repo = GitRepo(git_repo)

        # Add more files
        (git_repo / "subdir").mkdir()
        (git_repo / "subdir" / "nested.txt").write_text("nested content\n")
        (git_repo / "another.py").write_text("# python file\n")
        commit_changes(git_repo, "Add more files")

        files = repo.list_files("HEAD")

        assert "test.txt" in files
        assert "subdir/nested.txt" in files
        assert "another.py" in files

    def test_list_files_at_old_commit(self, git_repo):
        repo = GitRepo(git_repo)
        old_head = repo.head()

        # Add a new file
        (git_repo / "new_file.txt").write_text("new\n")
        commit_changes(git_repo, "Add new file")

        # Old commit should not have new file
        old_files = repo.list_files(old_head)
        assert "new_file.txt" not in old_files
        assert "test.txt" in old_files

        # New commit should have new file
        new_files = repo.list_files("HEAD")
        assert "new_file.txt" in new_files
