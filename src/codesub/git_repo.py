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

    def diff_patch(self, base: str, target: str) -> str:
        """
        Get unified diff between two refs.

        Uses -U0 for minimal context (just hunks).

        Args:
            base: Base ref.
            target: Target ref.

        Returns:
            Diff text (may be empty if no changes).
        """
        result = subprocess.run(
            ["git", "diff", "-U0", "--find-renames", base, target],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitError(f"git diff {base} {target}", result.stderr.strip())
        return result.stdout

    def diff_name_status(self, base: str, target: str) -> str:
        """
        Get name-status diff between two refs for rename detection.

        Args:
            base: Base ref.
            target: Target ref.

        Returns:
            Name-status output text.
        """
        result = subprocess.run(
            ["git", "diff", "--name-status", "-M", "--find-renames", base, target],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitError(f"git diff --name-status {base} {target}", result.stderr.strip())
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
