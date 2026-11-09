"""
tests.test_move_to_vault
~~~~~~~~~~~~~~~~~~~~~~~~
Unit and integration tests for the 'Move to Private Vault' feature.
"""

from unittest.mock import MagicMock
import pytest
from storista import create_app
from storista.services.github_service import GitHubService, is_vault_path, normalize_storage_path


@pytest.fixture
def mock_github_service():
    """Mock GitHubService for unit testing move-to-vault routes."""
    mock = MagicMock(spec=GitHubService)
    mock.normalize_storage_path.side_effect = normalize_storage_path
    mock.is_vault_path.side_effect = is_vault_path
    return mock


@pytest.fixture
def app(mock_github_service):
    """Test application configured with mock GitHubService."""
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-12345",
        "VAULT_PASSWORD": "cheese burger",
        "GITHUB_SERVICE": mock_github_service,
    })
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_is_vault_path_behavior():
    """Verify is_vault_path correctly identifies vault and non-vault items."""
    assert is_vault_path("vault") is True
    assert is_vault_path("storage/vault") is True
    assert is_vault_path("storage/vault/subfolder") is True
    assert is_vault_path("storage/vault/secret.txt") is True

    assert is_vault_path("") is False
    assert is_vault_path("storage") is False
    assert is_vault_path("storage/Photo.jpg") is False
    assert is_vault_path("subfolder/doc.pdf") is False
    assert is_vault_path("vault_notes") is False


def test_api_move_to_vault_missing_path(client):
    """POST /api/vault/move without path should return 400."""
    res = client.post("/api/vault/move", json={})
    assert res.status_code == 400
    assert "Missing required 'path' parameter" in res.get_json()["error"]


def test_api_move_to_vault_path_traversal(client):
    """POST /api/vault/move with directory traversal should return 403."""
    res = client.post("/api/vault/move", json={"path": "../secret.txt"})
    assert res.status_code == 403
    assert "Access denied" in res.get_json()["error"]


def test_api_move_to_vault_root_storage(client):
    """POST /api/vault/move targeting root storage should return 403."""
    res = client.post("/api/vault/move", json={"path": "storage"})
    assert res.status_code == 403
    assert "Cannot move root storage directory" in res.get_json()["error"]


def test_api_move_to_vault_already_in_vault(client):
    """POST /api/vault/move targeting item already in vault should return 400."""
    res = client.post("/api/vault/move", json={"path": "storage/vault/document.pdf"})
    assert res.status_code == 400
    assert "already inside the private vault" in res.get_json()["error"]


def test_api_move_to_vault_success(client, mock_github_service):
    """POST /api/vault/move successfully moves a file."""
    mock_github_service.move_to_vault.return_value = {
        "name": "photo.jpg",
        "source": "storage/photo.jpg",
        "destination": "storage/vault/photo.jpg",
        "is_dir": False,
    }

    res = client.post("/api/vault/move", json={"path": "photo.jpg"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "photo.jpg" in data["message"]
    assert data["destination"] == "storage/vault/photo.jpg"
    assert data["is_dir"] is False
    mock_github_service.move_to_vault.assert_called_once_with("photo.jpg")


def test_web_move_to_vault_success(client, mock_github_service):
    """POST /vault/move moves item and redirects with flash message."""
    mock_github_service.move_to_vault.return_value = {
        "name": "docs",
        "source": "storage/docs",
        "destination": "storage/vault/docs",
        "is_dir": True,
    }

    res = client.post("/vault/move", data={
        "path": "storage/docs",
        "current_folder": "",
    }, follow_redirects=True)

    assert res.status_code == 200
    mock_github_service.move_to_vault.assert_called_once_with("storage/docs")
    assert b"moved to Private Vault successfully" in res.data
