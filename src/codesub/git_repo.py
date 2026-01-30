"""Git repository wrapper for codesub."""

import subprocess
from pathlib import Path

from .errors import FileNotFoundAtRefError, GitError, NotAGitRepoError
from .utils import normalize_path


class GitRepo:
    """Wrapper for git operations."""

    def __init__(self, start_dir: str | Path = "."):
        """
        Initialize GitRepo by finding the repository root.

        Args:
            start_dir: Directory to start searching from.

        Raises:
            NotAGitRepoError: If not inside a git repository.
        """
        self._start_dir = Path(start_dir).resolve()
        self._root: Path | None = None

    @property
    def root(self) -> Path:
        """Get the repository root directory (cached)."""
        if self._root is None:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self._start_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise NotAGitRepoError(str(self._start_dir))
            self._root = Path(result.stdout.strip())
        return self._root

    def head(self) -> str:
        """Get the current HEAD commit hash."""
        return self.resolve_ref("HEAD")

    def commit_title(self, ref: str, max_length: int = 50) -> str:
        """
        Get the commit title (subject line) for a ref.

        Args:
            ref: Git ref (commit hash, branch name, etc.).
            max_length: Maximum length before truncation (0 = no limit).

        Returns:
            Commit subject line, possibly truncated with "...".
        """
        result = subprocess.run(
            ["git", "log", "--format=%s", "-n", "1", ref],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        title = result.stdout.strip()
        if max_length > 0 and len(title) > max_length:
            title = title[: max_length - 3] + "..."
        return title

    def resolve_ref(self, ref: str) -> str:
        """
        Resolve a git ref to a full commit hash.

        Args:
            ref: Git ref (e.g., "HEAD", "main", commit hash).

        Returns:
            Full commit hash.

        Raises:
            GitError: If ref cannot be resolved.
        """
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitError(f"git rev-parse {ref}", result.stderr.strip())
        return result.stdout.strip()

    def show_file(self, ref: str, path: str) -> list[str]:
        """
        Get file content at a specific ref.

        Args:
            ref: Git ref (commit hash, branch name, etc.).
            path: Repo-relative path to the file.

        Returns:
            List of lines (without trailing newlines).

        Raises:
            FileNotFoundAtRefError: If file doesn't exist at ref.
            GitError: If git command fails for other reasons.
        """
        path = normalize_path(path)
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "does not exist" in stderr or "exists on disk" in stderr:
                raise FileNotFoundAtRefError(path, ref)
            raise GitError(f"git show {ref}:{path}", stderr)

        # Split into lines, preserving empty lines but removing trailing newline
        content = result.stdout
        if content.endswith("\n"):
            content = content[:-1]
        if not content:
            return []
        return content.split("\n")

    def list_files(self, ref: str) -> list[str]:
        """
        List all tracked files at a specific ref.

        Args:
            ref: Git ref (commit hash, branch name, etc.).

        Returns:
            List of repo-relative file paths (excludes submodules).

        Raises:
            GitError: If git command fails.
        """
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitError(f"git ls-tree {ref}", result.stderr.strip())

        if not result.stdout.strip():
            return []
        return result.stdout.strip().split("\n")

    def diff_patch(self, base: str, target: str | None = None) -> str:
        """
        Get unified diff between two refs, or between a ref and working directory.

        Uses -U0 for minimal context (just hunks).

        Args:
            base: Base ref.
            target: Target ref, or None/empty for working directory.

        Returns:
            Diff text (may be empty if no changes).
        """
        if target:
            cmd = ["git", "diff", "-U0", "--find-renames", base, target]
        else:
            # Compare base to working directory (uncommitted changes)
            cmd = ["git", "diff", "-U0", "--find-renames", base]
        result = subprocess.run(
            cmd,
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitError(f"git diff {base} {target or '(working)'}", result.stderr.strip())
        return result.stdout

    def diff_name_status(self, base: str, target: str | None = None) -> str:
        """
        Get name-status diff between two refs, or between a ref and working directory.

        Args:
            base: Base ref.
            target: Target ref, or None/empty for working directory.

        Returns:
            Name-status output text.
        """
        if target:
            cmd = ["git", "diff", "--name-status", "-M", "--find-renames", base, target]
        else:
            cmd = ["git", "diff", "--name-status", "-M", "--find-renames", base]
        result = subprocess.run(
            cmd,
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitError(f"git diff --name-status {base} {target or '(working)'}", result.stderr.strip())
        return result.stdout

    def file_line_count(self, ref: str, path: str) -> int:
        """Get the number of lines in a file at a ref."""
        lines = self.show_file(ref, path)
        return len(lines)

    def relative_path(self, abs_path: str | Path) -> str:
        """
        Convert an absolute path to a repo-relative path.

        Args:
            abs_path: Absolute or relative path.

        Returns:
            Repo-relative POSIX path.
        """
        path = Path(abs_path).resolve()
        try:
            rel = path.relative_to(self.root)
            return normalize_path(str(rel))
        except ValueError:
            # Path is not inside repo, return as-is normalized
            return normalize_path(str(path))
