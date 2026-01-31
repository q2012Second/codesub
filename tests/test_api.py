"""Tests for the FastAPI API."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client_with_project(git_repo, temp_dir, monkeypatch):
    """Create test client with registered project."""
    # Set up a temporary data directory
    data_dir = temp_dir / "data"
    data_dir.mkdir()

    # Monkeypatch the DATA_DIR in both modules
    from codesub import project_store, config_store
    monkeypatch.setattr(project_store, "DATA_DIR", data_dir)
    monkeypatch.setattr(config_store, "DATA_DIR", data_dir)

    # Register the project
    from codesub.project_store import ProjectStore
    store = ProjectStore(config_dir=data_dir)
    project = store.add_project(path=str(git_repo))

    # Import and create the test client
    from codesub.api import app
    client = TestClient(app)

    return client, project.id


@pytest.fixture
def api_client(api_client_with_project):
    """Just the client for simple tests."""
    client, _ = api_client_with_project
    return client


@pytest.fixture
def project_id(api_client_with_project):
    """Just the project_id."""
    _, pid = api_client_with_project
    return pid


class TestHealthCheck:
    def test_health_with_projects(self, api_client):
        response = api_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "project_count" in data

    def test_health_no_projects(self, temp_dir, monkeypatch):
        """Test health check with no projects."""
        data_dir = temp_dir / "data"
        data_dir.mkdir()

        from codesub import project_store, config_store
        monkeypatch.setattr(project_store, "DATA_DIR", data_dir)
        monkeypatch.setattr(config_store, "DATA_DIR", data_dir)

        from codesub.api import app
        client = TestClient(app)

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["project_count"] == 0


class TestProjectSubscriptions:
    """Test project-scoped subscription endpoints."""

    def test_list_empty(self, api_client_with_project):
        client, project_id = api_client_with_project
        response = client.get(f"/api/projects/{project_id}/subscriptions")
        assert response.status_code == 200
        data = response.json()
        assert data["subscriptions"] == []
        assert data["count"] == 0
        assert "baseline_ref" in data

    def test_create_subscription(self, api_client_with_project):
        client, project_id = api_client_with_project
        response = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={
                "location": "test.txt:2-4",
                "label": "Important section",
                "description": "Watch this",
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["path"] == "test.txt"
        assert data["start_line"] == 2
        assert data["end_line"] == 4
        assert data["label"] == "Important section"
        assert data["description"] == "Watch this"
        assert data["active"] is True
        assert "id" in data
        assert data["anchors"] is not None

    def test_create_single_line(self, api_client_with_project):
        client, project_id = api_client_with_project
        response = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:3"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["start_line"] == 3
        assert data["end_line"] == 3

    def test_create_invalid_location_format(self, api_client_with_project):
        client, project_id = api_client_with_project
        response = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "invalid"}
        )
        assert response.status_code == 400
        assert "InvalidLocationError" in response.json().get("error_type", "")

    def test_create_file_not_found(self, api_client_with_project):
        client, project_id = api_client_with_project
        response = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "nonexistent.txt:1"}
        )
        assert response.status_code == 404

    def test_create_line_out_of_range(self, api_client_with_project):
        client, project_id = api_client_with_project
        response = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:100"}
        )
        assert response.status_code == 400
        assert "exceeds file length" in response.json()["detail"]

    def test_list_with_subscriptions(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create a subscription first
        create_response = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1-3", "label": "Test"}
        )
        assert create_response.status_code == 201

        # Now list
        response = client.get(f"/api/projects/{project_id}/subscriptions")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["subscriptions"][0]["label"] == "Test"

    def test_get_by_id(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Get
        response = client.get(f"/api/projects/{project_id}/subscriptions/{sub_id}")
        assert response.status_code == 200
        assert response.json()["id"] == sub_id

    def test_get_by_partial_id(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Get by first 8 chars
        response = client.get(f"/api/projects/{project_id}/subscriptions/{sub_id[:8]}")
        assert response.status_code == 200
        assert response.json()["id"] == sub_id

    def test_update_label(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1", "label": "Old"}
        )
        sub_id = create_resp.json()["id"]

        # Update
        response = client.patch(
            f"/api/projects/{project_id}/subscriptions/{sub_id}",
            json={"label": "New"}
        )
        assert response.status_code == 200
        assert response.json()["label"] == "New"

    def test_update_preserves_unset_fields(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create with label and description
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1", "label": "Label", "description": "Desc"}
        )
        sub_id = create_resp.json()["id"]

        # Update only label
        response = client.patch(
            f"/api/projects/{project_id}/subscriptions/{sub_id}",
            json={"label": "New Label"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "New Label"
        assert data["description"] == "Desc"  # Preserved

    def test_soft_delete(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Soft delete
        response = client.delete(f"/api/projects/{project_id}/subscriptions/{sub_id}")
        assert response.status_code == 200
        assert response.json()["active"] is False

        # Should not appear in default list
        list_resp = client.get(f"/api/projects/{project_id}/subscriptions")
        assert list_resp.json()["count"] == 0

        # Should appear with include_inactive
        list_resp = client.get(f"/api/projects/{project_id}/subscriptions?include_inactive=true")
        assert list_resp.json()["count"] == 1

    def test_hard_delete(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Hard delete
        response = client.delete(f"/api/projects/{project_id}/subscriptions/{sub_id}?hard=true")
        assert response.status_code == 200

        # Should not appear even with include_inactive
        list_resp = client.get(f"/api/projects/{project_id}/subscriptions?include_inactive=true")
        assert list_resp.json()["count"] == 0

    def test_reactivate(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create and deactivate
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]
        client.delete(f"/api/projects/{project_id}/subscriptions/{sub_id}")

        # Reactivate
        response = client.post(f"/api/projects/{project_id}/subscriptions/{sub_id}/reactivate")
        assert response.status_code == 200
        assert response.json()["active"] is True

    def test_reactivate_already_active(self, api_client_with_project):
        client, project_id = api_client_with_project
        # Create (already active)
        create_resp = client.post(
            f"/api/projects/{project_id}/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Try to reactivate
        response = client.post(f"/api/projects/{project_id}/subscriptions/{sub_id}/reactivate")
        assert response.status_code == 400
        assert "already active" in response.json()["detail"].lower()

    def test_not_found(self, api_client_with_project):
        client, project_id = api_client_with_project
        response = client.get(f"/api/projects/{project_id}/subscriptions/nonexistent")
        assert response.status_code == 404


class TestProjectNotFound:
    def test_subscriptions_project_not_found(self, temp_dir, monkeypatch):
        """Test that API returns 404 for non-existent project."""
        data_dir = temp_dir / "data"
        data_dir.mkdir()

        from codesub import project_store, config_store
        monkeypatch.setattr(project_store, "DATA_DIR", data_dir)
        monkeypatch.setattr(config_store, "DATA_DIR", data_dir)

        from codesub.api import app
        client = TestClient(app)

        response = client.get("/api/projects/nonexistent/subscriptions")
        assert response.status_code == 404
