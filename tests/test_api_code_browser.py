"""Tests for the Code Browser API endpoints."""

import pytest
from fastapi.testclient import TestClient

from .conftest import commit_changes


@pytest.fixture
def project_client(git_repo, monkeypatch):
    """Create test client with a registered project."""
    monkeypatch.chdir(git_repo)

    # Initialize codesub
    from codesub.config_store import ConfigStore
    from codesub.git_repo import GitRepo
    from codesub.project_store import ProjectStore

    repo = GitRepo()
    store = ConfigStore(repo.root)
    store.init(repo.head())

    # Register the project
    project_store = ProjectStore()
    project = project_store.add_project(str(git_repo), "test-project")

    from codesub.api import app

    client = TestClient(app)
    return client, project.id


@pytest.fixture
def project_with_python(git_repo, monkeypatch):
    """Create a project with Python files for semantic testing."""
    monkeypatch.chdir(git_repo)

    # Create Python file
    python_file = git_repo / "example.py"
    python_file.write_text('''"""Example module."""

API_VERSION = "1.0.0"

class User:
    """User class."""

    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        return f"Hello, {self.name}"


def helper_function():
    pass
''')
    commit_changes(git_repo, "Add Python file")

    # Initialize codesub
    from codesub.config_store import ConfigStore
    from codesub.git_repo import GitRepo
    from codesub.project_store import ProjectStore

    repo = GitRepo()
    store = ConfigStore(repo.root)
    store.init(repo.head())

    # Register the project
    project_store = ProjectStore()
    project = project_store.add_project(str(git_repo), "test-project")

    from codesub.api import app

    client = TestClient(app)
    return client, project.id


class TestListProjectFiles:
    """Tests for GET /api/projects/{project_id}/files"""

    def test_list_files_basic(self, project_client):
        """Lists git-tracked files at baseline."""
        client, project_id = project_client
        response = client.get(f"/api/projects/{project_id}/files")

        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "total" in data
        assert "has_more" in data
        assert data["total"] >= 1
        # test.txt from git_repo fixture
        paths = [f["path"] for f in data["files"]]
        assert "test.txt" in paths

    def test_list_files_search(self, project_client):
        """Filters files by search term."""
        client, project_id = project_client
        response = client.get(f"/api/projects/{project_id}/files?search=test")

        assert response.status_code == 200
        data = response.json()
        assert all("test" in f["path"].lower() for f in data["files"])

    def test_list_files_extensions(self, project_with_python):
        """Filters files by extension."""
        client, project_id = project_with_python
        response = client.get(f"/api/projects/{project_id}/files?extensions=.py")

        assert response.status_code == 200
        data = response.json()
        assert all(f["extension"] == ".py" for f in data["files"])
        assert any(f["path"] == "example.py" for f in data["files"])

    def test_list_files_text_only_excludes_txt_by_default(self, project_client):
        """Default text_only filter includes .txt files."""
        client, project_id = project_client
        response = client.get(f"/api/projects/{project_id}/files")

        assert response.status_code == 200
        data = response.json()
        # .txt is in TEXT_EXTENSIONS
        paths = [f["path"] for f in data["files"]]
        assert "test.txt" in paths

    def test_list_files_pagination(self, project_client):
        """Supports pagination."""
        client, project_id = project_client
        response = client.get(f"/api/projects/{project_id}/files?limit=1&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) <= 1

    def test_list_files_project_not_found(self, project_client):
        """Returns 404 for unknown project."""
        client, _ = project_client
        response = client.get("/api/projects/nonexistent-id/files")

        assert response.status_code == 404


class TestGetFileContent:
    """Tests for GET /api/projects/{project_id}/file-content"""

    def test_get_content_basic(self, project_client):
        """Returns file content with metadata."""
        client, project_id = project_client
        response = client.get(
            f"/api/projects/{project_id}/file-content?path=test.txt"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "test.txt"
        assert "lines" in data
        assert "total_lines" in data
        assert data["total_lines"] == 5
        assert len(data["lines"]) == 5
        assert data["lines"][0] == "line 1"

    def test_get_content_detects_python_language(self, project_with_python):
        """Detects language for supported files."""
        client, project_id = project_with_python
        response = client.get(
            f"/api/projects/{project_id}/file-content?path=example.py"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "python"
        assert data["supports_semantic"] is True

    def test_get_content_unsupported_language(self, project_client):
        """Handles unsupported language gracefully."""
        client, project_id = project_client
        response = client.get(
            f"/api/projects/{project_id}/file-content?path=test.txt"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["language"] is None
        assert data["supports_semantic"] is False

    def test_get_content_file_not_found(self, project_client):
        """Returns 404 for missing file."""
        client, project_id = project_client
        response = client.get(
            f"/api/projects/{project_id}/file-content?path=nonexistent.py"
        )

        assert response.status_code == 404


class TestGetFileSymbols:
    """Tests for GET /api/projects/{project_id}/file-symbols"""

    def test_get_symbols_python(self, project_with_python):
        """Returns constructs for Python file."""
        client, project_id = project_with_python
        response = client.get(
            f"/api/projects/{project_id}/file-symbols?path=example.py"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "python"
        assert isinstance(data["constructs"], list)
        assert len(data["constructs"]) > 0

        # Check construct structure
        for c in data["constructs"]:
            assert "kind" in c
            assert "qualname" in c
            assert "start_line" in c
            assert "end_line" in c
            assert "target" in c

        # Check specific constructs
        # Note: Python indexer returns module-level variables and class methods
        qualnames = [c["qualname"] for c in data["constructs"]]
        assert "API_VERSION" in qualnames
        assert "User.__init__" in qualnames
        assert "User.greet" in qualnames

    def test_get_symbols_filter_by_kind(self, project_with_python):
        """Filters constructs by kind."""
        client, project_id = project_with_python
        response = client.get(
            f"/api/projects/{project_id}/file-symbols?path=example.py&kind=method"
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["kind"] == "method" for c in data["constructs"])

    def test_get_symbols_target_format(self, project_with_python):
        """Target string is correctly formatted with kind."""
        client, project_id = project_with_python
        response = client.get(
            f"/api/projects/{project_id}/file-symbols?path=example.py"
        )

        assert response.status_code == 200
        data = response.json()

        # Find the User.greet method - target now includes kind
        greet = next((c for c in data["constructs"] if c["qualname"] == "User.greet"), None)
        assert greet is not None
        assert greet["target"] == "example.py::method:User.greet"

    def test_get_symbols_unsupported_language(self, project_client):
        """Returns 400 for unsupported language."""
        client, project_id = project_client
        response = client.get(
            f"/api/projects/{project_id}/file-symbols?path=test.txt"
        )

        assert response.status_code == 400

    def test_get_symbols_file_not_found(self, project_with_python):
        """Returns 404 for missing file."""
        client, project_id = project_with_python
        response = client.get(
            f"/api/projects/{project_id}/file-symbols?path=nonexistent.py"
        )

        assert response.status_code == 404
