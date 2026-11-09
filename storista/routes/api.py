"""
storista.routes.api
~~~~~~~~~~~~~~~~~~~
REST API and streaming download routes for Storista.
Provides sandboxed JSON endpoints and direct authenticated file downloads.
"""

import urllib.parse
from flask import Blueprint, jsonify, Response, request, session, current_app, stream_with_context
from github import GithubException

from storista.services.github_service import (
    get_github_service,
    normalize_storage_path,
    is_vault_path,
    extract_github_error_message,
)

api_bp = Blueprint("api", __name__)


def check_vault_authorized(norm_path: str) -> bool:
    """Verify if the caller has valid authorization to access vault paths."""
    if not is_vault_path(norm_path):
        return True
    if session.get("vault_access") is True:
        return True
    configured_password = current_app.config.get("VAULT_PASSWORD", "cheese burger")
    query_pwd = request.args.get("password")
    if query_pwd and query_pwd.strip().lower() == configured_password.strip().lower():
        return True
    return False


@api_bp.route("/api/files/<path:file_path>", methods=["GET"])
def get_file_info(file_path: str):
    """
    Retrieve metadata for a single file.
    Accepts both bare paths ('Photo-1.jpeg') and prefixed paths ('storage/Photo-1.jpeg').
    Returns 403 if path lies outside storage sandbox or vault is locked.
    """
    service = get_github_service()
    try:
        norm_path = normalize_storage_path(file_path)
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403

    if not check_vault_authorized(norm_path):
        return jsonify({"error": "Vault access denied"}), 403

    try:
        info = service.get_file_info(file_path)
        return jsonify(info), 200
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403
    except IsADirectoryError:
        return jsonify({"error": "Path is a directory"}), 400
    except GithubException as e:
        status_code = e.status if e.status and 400 <= e.status < 600 else 404
        return jsonify({"error": extract_github_error_message(e)}), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route("/api/files/<path:file_path>", methods=["DELETE"])
def delete_file(file_path: str):
    """
    Delete a single file from storage.
    Accepts both bare paths ('file.txt') and prefixed paths ('storage/file.txt').
    Returns 403 if path lies outside storage sandbox or vault is locked.
    """
    service = get_github_service()
    try:
        norm_path = normalize_storage_path(file_path)
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403

    if not check_vault_authorized(norm_path):
        return jsonify({"error": "Vault access denied"}), 403

    try:
        service.delete_file(file_path)
        return jsonify({
            "status": "success",
            "message": f"File '{file_path}' deleted successfully"
        }), 200
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403
    except IsADirectoryError:
        return jsonify({"error": "Use folder delete endpoint for directories"}), 400
    except GithubException as e:
        status_code = e.status if e.status and 400 <= e.status < 600 else 404
        return jsonify({"error": extract_github_error_message(e)}), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/folders/<path:folder_path>", methods=["GET"])
def list_folder(folder_path: str):
    """
    List contents of a directory as JSON.
    Normalizes path to resolve the legacy 'storage/storage/...' double-prefix bug.
    Returns 403 if path lies outside storage sandbox or vault is locked.
    """
    service = get_github_service()
    try:
        norm_path = normalize_storage_path(folder_path)
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403

    if not check_vault_authorized(norm_path):
        return jsonify({"error": "Vault access denied"}), 403

    try:
        files = service.list_contents(folder_path)
        return jsonify({
            "folder": folder_path,
            "files": files
        }), 200
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403
    except GithubException as e:
        status_code = e.status if e.status and 400 <= e.status < 600 else 404
        return jsonify({"error": extract_github_error_message(e)}), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/folders/<path:folder_path>", methods=["DELETE"])
def delete_folder(folder_path: str):
    """
    Recursively delete a folder and all its contents.
    Accepts both bare paths ('sub') and prefixed paths ('storage/sub').
    Returns 403 if path lies outside storage sandbox, targets storage root, or vault is locked.
    """
    service = get_github_service()
    try:
        norm_path = normalize_storage_path(folder_path)
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403

    if norm_path == "storage":
        return jsonify({"error": "Cannot delete root storage directory"}), 403

    if not check_vault_authorized(norm_path):
        return jsonify({"error": "Vault access denied"}), 403

    try:
        service.delete_folder(folder_path)
        return jsonify({
            "status": "success",
            "message": f"Folder '{folder_path}' deleted successfully"
        }), 200
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except GithubException as e:
        status_code = e.status if e.status and 400 <= e.status < 600 else 500
        return jsonify({"error": extract_github_error_message(e)}), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/download/<path:file_path>", methods=["GET"])
def download_file(file_path: str):
    """
    Stream file content with Content-Disposition attachment header.
    Works for public and private repositories alike via authenticated streaming.
    Returns 403 if path lies outside storage sandbox or vault is locked.
    """
    service = get_github_service()
    try:
        norm_path = normalize_storage_path(file_path)
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403

    if not check_vault_authorized(norm_path):
        return jsonify({"error": "Vault access denied"}), 403

    try:
        filename, mime_type, content_length, generator = service.stream_file(file_path)

        ascii_filename = filename.encode("ascii", "ignore").decode("ascii") or "file"
        encoded_filename = urllib.parse.quote(filename)
        disposition = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'

        response = Response(stream_with_context(generator), mimetype=mime_type)
        response.headers["Content-Disposition"] = disposition
        if content_length:
            response.headers["Content-Length"] = str(content_length)
        response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403
    except IsADirectoryError:
        return jsonify({"error": "Cannot download directory directly"}), 400
    except GithubException as e:
        status_code = e.status if e.status and 400 <= e.status < 600 else 404
        return jsonify({"error": extract_github_error_message(e)}), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route("/api/vault/move", methods=["POST"])
def move_to_vault():
    """
    Move a file or folder into the private vault (storage/vault/).
    Accepts JSON payload: {"path": "file.txt"} or form parameter.
    Returns 400 if item is already in vault or path is missing.
    Returns 403 if path lies outside storage sandbox.
    """
    payload = request.get_json(silent=True) or {}
    item_path = payload.get("path") or request.form.get("path", "").strip()

    if not item_path:
        return jsonify({"error": "Missing required 'path' parameter"}), 400

    service = get_github_service()
    try:
        norm_path = normalize_storage_path(item_path)
    except PermissionError:
        return jsonify({"error": "Access denied"}), 403

    if norm_path == "storage":
        return jsonify({"error": "Cannot move root storage directory"}), 403

    if is_vault_path(norm_path):
        return jsonify({"error": "Item is already inside the private vault"}), 400

    try:
        result = service.move_to_vault(item_path)
        return jsonify({
            "status": "success",
            "message": f"'{result['name']}' moved to Private Vault successfully",
            "name": result["name"],
            "destination": result["destination"],
            "is_dir": result["is_dir"]
        }), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except (FileNotFoundError, IsADirectoryError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    except GithubException as e:
        status_code = e.status if e.status and 400 <= e.status < 600 else 500
        return jsonify({"error": extract_github_error_message(e)}), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

