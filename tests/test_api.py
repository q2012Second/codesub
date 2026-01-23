"""Tests for the FastAPI API."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(git_repo, monkeypatch):
    """Create test client with git repo context."""
    # Change to the git repo directory so GitRepo() finds it
    monkeypatch.chdir(git_repo)

    # Initialize codesub
    from codesub.config_store import ConfigStore
    from codesub.git_repo import GitRepo

    repo = GitRepo()
    store = ConfigStore(repo.root)
    store.init(repo.head())

    # Now import and create the test client
    from codesub.api import app

    return TestClient(app)


class TestHealthCheck:
    def test_health_initialized(self, api_client):
        response = api_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["config_initialized"] is True
        assert "baseline_ref" in data

    def test_health_not_initialized(self, git_repo, monkeypatch):
        """Test health check when config is not initialized."""
        monkeypatch.chdir(git_repo)
        from codesub.api import app

        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["config_initialized"] is False


class TestListSubscriptions:
    def test_empty_list(self, api_client):
        response = api_client.get("/api/subscriptions")
        assert response.status_code == 200
        data = response.json()
        assert data["subscriptions"] == []
        assert data["count"] == 0
        assert "baseline_ref" in data

    def test_list_with_subscriptions(self, api_client):
        # Create a subscription first
        create_response = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1-3", "label": "Test"}
        )
        assert create_response.status_code == 201

        # Now list
        response = api_client.get("/api/subscriptions")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["subscriptions"][0]["label"] == "Test"

    def test_list_excludes_inactive_by_default(self, api_client):
        # Create and deactivate a subscription
        create_response = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_response.json()["id"]
        api_client.delete(f"/api/subscriptions/{sub_id}")

        # List without include_inactive
        response = api_client.get("/api/subscriptions")
        assert response.json()["count"] == 0

        # List with include_inactive
        response = api_client.get("/api/subscriptions?include_inactive=true")
        assert response.json()["count"] == 1


class TestCreateSubscription:
    def test_create_success(self, api_client):
        response = api_client.post(
            "/api/subscriptions",
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

    def test_create_single_line(self, api_client):
        response = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:3"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["start_line"] == 3
        assert data["end_line"] == 3

    def test_create_invalid_location_format(self, api_client):
        response = api_client.post(
            "/api/subscriptions",
            json={"location": "invalid"}
        )
        assert response.status_code == 400
        assert "InvalidLocationError" in response.json().get("error_type", "")

    def test_create_file_not_found(self, api_client):
        response = api_client.post(
            "/api/subscriptions",
            json={"location": "nonexistent.txt:1"}
        )
        assert response.status_code == 404

    def test_create_line_out_of_range(self, api_client):
        response = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:100"}
        )
        assert response.status_code == 400
        assert "exceeds file length" in response.json()["detail"]

    def test_create_with_context(self, api_client):
        response = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:3", "context": 1}
        )
        assert response.status_code == 201
        data = response.json()
        # With context=1, should have at most 1 line before/after
        assert len(data["anchors"]["context_before"]) <= 1
        assert len(data["anchors"]["context_after"]) <= 1

    def test_create_context_out_of_range(self, api_client):
        response = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1", "context": 15}
        )
        # Pydantic validation should reject context > 10
        assert response.status_code == 422


class TestGetSubscription:
    def test_get_by_full_id(self, api_client):
        # Create
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Get
        response = api_client.get(f"/api/subscriptions/{sub_id}")
        assert response.status_code == 200
        assert response.json()["id"] == sub_id

    def test_get_by_partial_id(self, api_client):
        # Create
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Get by first 8 chars
        response = api_client.get(f"/api/subscriptions/{sub_id[:8]}")
        assert response.status_code == 200
        assert response.json()["id"] == sub_id

    def test_get_not_found(self, api_client):
        response = api_client.get("/api/subscriptions/nonexistent")
        assert response.status_code == 404


class TestUpdateSubscription:
    def test_update_label(self, api_client):
        # Create
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1", "label": "Old"}
        )
        sub_id = create_resp.json()["id"]

        # Update
        response = api_client.patch(
            f"/api/subscriptions/{sub_id}",
            json={"label": "New"}
        )
        assert response.status_code == 200
        assert response.json()["label"] == "New"

    def test_update_description(self, api_client):
        # Create
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Update
        response = api_client.patch(
            f"/api/subscriptions/{sub_id}",
            json={"description": "New description"}
        )
        assert response.status_code == 200
        assert response.json()["description"] == "New description"

    def test_update_empty_string_clears_field(self, api_client):
        # Create with label
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1", "label": "Old Label"}
        )
        sub_id = create_resp.json()["id"]

        # Update with empty string should clear
        response = api_client.patch(
            f"/api/subscriptions/{sub_id}",
            json={"label": ""}
        )
        assert response.status_code == 200
        assert response.json()["label"] is None

    def test_update_preserves_unset_fields(self, api_client):
        # Create with label and description
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1", "label": "Label", "description": "Desc"}
        )
        sub_id = create_resp.json()["id"]

        # Update only label
        response = api_client.patch(
            f"/api/subscriptions/{sub_id}",
            json={"label": "New Label"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "New Label"
        assert data["description"] == "Desc"  # Preserved

    def test_update_not_found(self, api_client):
        response = api_client.patch(
            "/api/subscriptions/nonexistent",
            json={"label": "Test"}
        )
        assert response.status_code == 404


class TestDeleteSubscription:
    def test_soft_delete(self, api_client):
        # Create
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Soft delete
        response = api_client.delete(f"/api/subscriptions/{sub_id}")
        assert response.status_code == 200
        assert response.json()["active"] is False

        # Should not appear in default list
        list_resp = api_client.get("/api/subscriptions")
        assert list_resp.json()["count"] == 0

        # Should appear with include_inactive
        list_resp = api_client.get("/api/subscriptions?include_inactive=true")
        assert list_resp.json()["count"] == 1

    def test_hard_delete(self, api_client):
        # Create
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Hard delete
        response = api_client.delete(f"/api/subscriptions/{sub_id}?hard=true")
        assert response.status_code == 200

        # Should not appear even with include_inactive
        list_resp = api_client.get("/api/subscriptions?include_inactive=true")
        assert list_resp.json()["count"] == 0

    def test_delete_not_found(self, api_client):
        response = api_client.delete("/api/subscriptions/nonexistent")
        assert response.status_code == 404


class TestReactivateSubscription:
    def test_reactivate(self, api_client):
        # Create and deactivate
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]
        api_client.delete(f"/api/subscriptions/{sub_id}")

        # Reactivate
        response = api_client.post(f"/api/subscriptions/{sub_id}/reactivate")
        assert response.status_code == 200
        assert response.json()["active"] is True

    def test_reactivate_already_active(self, api_client):
        # Create (already active)
        create_resp = api_client.post(
            "/api/subscriptions",
            json={"location": "test.txt:1"}
        )
        sub_id = create_resp.json()["id"]

        # Try to reactivate
        response = api_client.post(f"/api/subscriptions/{sub_id}/reactivate")
        assert response.status_code == 400
        assert "already active" in response.json()["detail"].lower()

    def test_reactivate_not_found(self, api_client):
        response = api_client.post("/api/subscriptions/nonexistent/reactivate")
        assert response.status_code == 404


class TestConfigNotInitialized:
    def test_list_when_not_initialized(self, git_repo, monkeypatch):
        """Test that API returns 409 when config is not initialized."""
        monkeypatch.chdir(git_repo)
        from codesub.api import app

        client = TestClient(app)
        response = client.get("/api/subscriptions")
        assert response.status_code == 409
        assert "init" in response.json()["detail"].lower()
