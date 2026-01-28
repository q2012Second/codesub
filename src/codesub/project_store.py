"""Project storage for codesub."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config_store import ConfigStore
from .errors import InvalidProjectPathError, ProjectNotFoundError
from .git_repo import GitRepo
from .models import Project, _utc_now

# Local data directory within the codesub project
DATA_DIR = Path(__file__).parent.parent.parent / "data"
PROJECTS_FILE = "projects.json"


class ProjectStore:
    """Manages project registration and storage."""

    def __init__(self, config_dir: Path | None = None):
        """
        Initialize ProjectStore.

        Args:
            config_dir: Override config directory (for testing).
        """
        self.config_dir = config_dir or DATA_DIR
        self.config_path = self.config_dir / PROJECTS_FILE

    def _ensure_dir(self) -> None:
        """Ensure config directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        """Acquire exclusive lock on the projects file for read-modify-write operations."""
        self._ensure_dir()
        lock_path = self.config_dir / ".projects.lock"
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_data(self) -> dict[str, Any]:
        """Load projects data from disk."""
        if not self.config_path.exists():
            return {"schema_version": 1, "projects": []}

        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_data(self, data: dict[str, Any]) -> None:
        """Save projects data to disk atomically."""
        self._ensure_dir()

        fd, temp_path = tempfile.mkstemp(
            dir=self.config_dir, prefix=".projects_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(temp_path, self.config_path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def list_projects(self) -> list[Project]:
        """List all registered projects."""
        data = self._load_data()
        return [Project.from_dict(p) for p in data.get("projects", [])]

    def get_project(self, project_id: str) -> Project:
        """
        Get a project by ID.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
        """
        projects = self.list_projects()
        for p in projects:
            if p.id == project_id:
                return p
        raise ProjectNotFoundError(project_id)

    def add_project(self, path: str, name: str | None = None) -> Project:
        """
        Add a new project.

        Args:
            path: Path to the git repository (absolute, relative, or with ~).
            name: Display name (defaults to directory name).

        Returns:
            The created Project.

        Raises:
            InvalidProjectPathError: If path is invalid.
        """
        # Expand ~ and resolve to absolute path
        abs_path = Path(path).expanduser().resolve()

        if not abs_path.exists():
            raise InvalidProjectPathError(str(abs_path), "path does not exist")

        if not abs_path.is_dir():
            raise InvalidProjectPathError(str(abs_path), "path is not a directory")

        # Validate it's a git repo
        try:
            repo = GitRepo(abs_path)
            _ = repo.root  # Force resolution
        except Exception:
            raise InvalidProjectPathError(str(abs_path), "not a git repository")

        # Validate codesub is initialized
        store = ConfigStore(repo.root)
        if not store.exists():
            raise InvalidProjectPathError(
                str(abs_path), "codesub not initialized (run 'codesub init' in the repo)"
            )

        # Use file lock to prevent race conditions during concurrent adds
        with self._lock():
            # Check for duplicates (inside lock to ensure consistency)
            data = self._load_data()
            for p in data.get("projects", []):
                if Path(p["path"]).resolve() == abs_path:
                    raise InvalidProjectPathError(
                        str(abs_path), f"project already registered with ID {p['id']}"
                    )

            # Create project
            project_name = name or abs_path.name
            project = Project.create(name=project_name, path=str(abs_path))

            # Save
            data["projects"].append(project.to_dict())
            self._save_data(data)

        return project

    def remove_project(self, project_id: str) -> Project:
        """
        Remove a project from the registry.

        Args:
            project_id: Project ID.

        Returns:
            The removed Project.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
        """
        with self._lock():
            data = self._load_data()
            projects = data.get("projects", [])

            for i, p in enumerate(projects):
                if p["id"] == project_id:
                    removed = Project.from_dict(projects.pop(i))
                    self._save_data(data)
                    return removed

            raise ProjectNotFoundError(project_id)

    def update_project(self, project_id: str, name: str) -> Project:
        """
        Update a project's name.

        Args:
            project_id: Project ID.
            name: New display name.

        Returns:
            The updated Project.

        Raises:
            ProjectNotFoundError: If project doesn't exist.
        """
        with self._lock():
            data = self._load_data()
            projects = data.get("projects", [])

            for p in projects:
                if p["id"] == project_id:
                    p["name"] = name
                    p["updated_at"] = _utc_now()
                    self._save_data(data)
                    return Project.from_dict(p)

            raise ProjectNotFoundError(project_id)

    def get_project_status(self, project_id: str) -> dict[str, Any]:
        """
        Get detailed status for a project.

        Returns dict with:
        - project: Project data
        - subscription_count: Number of active subscriptions
        - baseline_ref: Current baseline ref
        - path_exists: Whether path still exists
        - codesub_initialized: Whether .codesub exists
        """
        project = self.get_project(project_id)
        abs_path = Path(project.path)

        status: dict[str, Any] = {
            "project": project.to_dict(),
            "path_exists": abs_path.exists(),
            "codesub_initialized": False,
            "subscription_count": 0,
            "baseline_ref": None,
        }

        if not status["path_exists"]:
            return status

        try:
            repo = GitRepo(abs_path)
            store = ConfigStore(repo.root)
            status["codesub_initialized"] = store.exists()

            if store.exists():
                config = store.load()
                status["subscription_count"] = len(
                    [s for s in config.subscriptions if s.active]
                )
                status["baseline_ref"] = config.repo.baseline_ref
        except Exception:
            pass

        return status
