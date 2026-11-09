"""
storista.routes.web
~~~~~~~~~~~~~~~~~~~
Web UI routes for Storista: browsing, uploads, folder creation, and vault authentication.
"""

from typing import Optional
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, current_app
)
from github import GithubException

from storista.services.github_service import (
    get_github_service,
    normalize_storage_path,
    get_parent_folder,
    is_vault_path,
    sanitize_filename,
    extract_github_error_message,
)

web_bp = Blueprint("web", __name__)


def is_vault_locked(folder: Optional[str]) -> bool:
    """Check if the given folder requires vault authentication."""
    if not is_vault_path(folder):
        return False

    configured_password = current_app.config.get("VAULT_PASSWORD", "cheese burger")

    # Support query parameter authentication
    query_pwd = request.args.get("password")
    if query_pwd and query_pwd.strip().lower() == configured_password.strip().lower():
        return False

    # Check cryptographically signed session
    if session.get("vault_access") is True:
        return False

    return True


@web_bp.route("/", defaults={"folder": ""})
@web_bp.route("/browse/<path:folder>")
def index(folder: str = ""):
    """Main dashboard displaying files, folders, and navigation breadcrumbs."""
    service = get_github_service()

    # Vault Security Check
    if is_vault_locked(folder):
        return render_template(
            "index.html",
            files=[],
            current_folder=folder,
            parent_folder="",
            needs_auth=True
        )

    # Fetch contents from GitHub service
    files = service.list_contents(folder)

    # Calculate parent folder path for navigation
    try:
        norm_folder = normalize_storage_path(folder)
        parent = get_parent_folder(norm_folder)
    except PermissionError:
        parent = None

    return render_template(
        "index.html",
        files=files,
        current_folder=folder,
        parent_folder=parent,
        needs_auth=False
    )


@web_bp.route("/auth/vault", methods=["POST"])
def auth_vault():
    """Verify password for vault access and establish session."""
    password = request.form.get("password", "").strip().lower()
    folder = request.form.get("folder", "")
    configured_password = current_app.config.get("VAULT_PASSWORD", "cheese burger").strip().lower()

    if password == configured_password:
        # Establish cryptographically signed session
        session["vault_access"] = True
        return redirect(url_for("web.index", folder=folder))

    flash("Wrong! You clearly don't know the vibes. 💀")
    return redirect(url_for("web.index", folder=folder))


@web_bp.route("/upload", methods=["POST"])
def upload():
    """Handle file upload from local multipart payload or remote URL."""
    service = get_github_service()
    folder = request.form.get("folder", "").strip("/")

    # Vault Security Check
    if is_vault_locked(folder):
        flash("Vault is locked. Access denied.")
        return redirect(url_for("web.index", folder=folder)), 403

    # Storage Sandbox Pre-validation (Fail-Fast)
    normalize_storage_path(folder)

    url = request.form.get("url", "").strip()
    file = request.files.get("file")
    max_file_size = current_app.config.get("MAX_FILE_SIZE", 50 * 1024 * 1024)

    data: Optional[bytes] = None
    filename: Optional[str] = None

    if url:
        # Remote URL import with SSRF validation and bounded streaming
        try:
            filename, data = service.download_from_url(url, max_size=max_file_size)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("web.index", folder=folder))
        except Exception as e:
            flash(f"Failed to download from URL: {str(e)}")
            return redirect(url_for("web.index", folder=folder))

    elif file and file.filename:
        # Local multipart file upload
        data = file.read()
        filename = sanitize_filename(file.filename)

    else:
        flash("No file or URL provided.")
        return redirect(url_for("web.index", folder=folder))

    # Size verification
    if len(data) > max_file_size:
        flash(f"File too large. Max size: {service.format_bytes(max_file_size)}")
        return redirect(url_for("web.index", folder=folder))

    # Commit via GitHub service
    try:
        result = service.upload_file(filename=filename, data=data, folder=folder)
        if result.get("updated"):
            flash(f"File '{filename}' updated successfully.")
        else:
            flash(f"File '{filename}' uploaded successfully.")
    except IsADirectoryError:
        flash(f"Cannot upload '{filename}': a folder with that name already exists.")
    except GithubException as e:
        error_msg = extract_github_error_message(e)
        current_app.logger.error(f"GitHub upload error: {error_msg}")
        flash(f"GitHub error: {error_msg}")

    return redirect(url_for("web.index", folder=folder))


@web_bp.route("/create_folder", methods=["POST"])
def create_folder():
    """Create a new folder in storage by placing a .gitkeep marker."""
    service = get_github_service()
    folder = request.form.get("folder", "").strip("/")

    # Storage Sandbox Pre-validation (Fail-Fast)
    normalize_storage_path(folder)

    raw_name = request.form.get("new_folder_name", "").strip()
    new_folder_name = sanitize_filename(raw_name)

    if not new_folder_name or not raw_name:
        flash("Folder name is required.")
        return redirect(url_for("web.index", folder=folder))

    target_folder = f"{folder}/{new_folder_name}".strip("/") if folder else new_folder_name
    if is_vault_locked(folder) or is_vault_locked(target_folder):
        flash("Vault is locked. Access denied.")
        return redirect(url_for("web.index", folder=folder)), 403

    try:
        service.create_folder(folder=folder, folder_name=new_folder_name)
        flash(f"Folder '{new_folder_name}' created successfully.")
    except FileExistsError:
        flash("Folder already exists.")
    except GithubException as e:
        error_msg = extract_github_error_message(e)
        current_app.logger.error(f"GitHub create folder error: {error_msg}")
        flash(f"Failed to create folder: {error_msg}")

    return redirect(url_for("web.index", folder=folder))
