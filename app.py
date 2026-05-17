import os
import mimetypes
import requests
import re
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional

from flask import Flask, request, jsonify, render_template, abort, redirect, url_for, flash
from github import Github, GithubException, ContentFile
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

class Config:
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    GITHUB_REPO = os.environ.get("GITHUB_REPO")
    GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
    STORAGE_DIR = "storage"
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-change-me")

    @classmethod
    def validate(cls):
        if not (cls.GITHUB_TOKEN and cls.GITHUB_REPO):
            raise RuntimeError("Set GITHUB_TOKEN and GITHUB_REPO env vars before running.")

# --- Initialization ---
Config.validate()
g = Github(Config.GITHUB_TOKEN)
repo = g.get_repo(Config.GITHUB_REPO)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_FILE_SIZE

# --- Helpers ---

def format_bytes(size: int) -> str:
    """Format bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def get_direct_download_url(file_path: str) -> str:
    """Get direct GitHub raw content URL."""
    return f"https://raw.githubusercontent.com/{Config.GITHUB_REPO}/{Config.GITHUB_BRANCH}/{file_path}"

def get_mime_type(filename: str) -> str:
    """Get MIME type for file."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'

def get_storage_path(filename: str, folder: str = "") -> str:
    """Construct full path for file in storage."""
    folder = folder.strip().strip("/")
    filename = secure_filename(filename)
    if folder:
        return f"{Config.STORAGE_DIR}/{folder}/{filename}"
    return f"{Config.STORAGE_DIR}/{filename}"

def list_repo_contents(folder: str = "") -> List[Dict[str, Any]]:
    """List all files and folders in given directory from GitHub."""
    folder_path = f"{Config.STORAGE_DIR}/{folder}".strip("/")
    
    try:
        contents = repo.get_contents(folder_path, ref=Config.GITHUB_BRANCH)
        if not isinstance(contents, list):
            contents = [contents]
        
        items = []
        for c in contents:
            if c.name == ".gitkeep":
                continue
            
            item = {
                "name": c.name,
                "path": c.path,
                "is_dir": c.type == "dir",
            }
            
            if c.type == "file":
                item.update({
                    "size": c.size,
                    "size_formatted": format_bytes(c.size),
                    "download_url": get_direct_download_url(c.path),
                    "mime_type": get_mime_type(c.name),
                })
            
            items.append(item)
        
        # Sort: directories first, then files
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return items
    except GithubException as e:
        app.logger.error(f"GitHub error listing contents of '{folder_path}': {e}")
        return []

# --- Routes ---

@app.route("/", defaults={"folder": ""})
@app.route("/browse/<path:folder>")
def index(folder: str):
    """Main page displaying files and folders."""
    files = list_repo_contents(folder)
    
    # Calculate parent folder path
    parent = None
    if folder:
        parts = folder.strip("/").split("/")
        parent = "/".join(parts[:-1]) if len(parts) > 1 else ""
    
    return render_template(
        "index.html",
        files=files,
        current_folder=folder,
        parent_folder=parent
    )

@app.route("/upload", methods=["POST"])
def upload():
    """Handle file upload from local file or URL."""
    folder = request.form.get("folder", "").strip("/")
    url = request.form.get("url", "").strip()
    file = request.files.get("file")
    data = None
    filename = None

    # Option 1: Download from URL
    if url:
        try:
            with requests.get(url, timeout=30, stream=True) as r:
                r.raise_for_status()
                content_length = r.headers.get('content-length')
                if content_length and int(content_length) > Config.MAX_FILE_SIZE:
                    flash(f"File too large. Max size: {format_bytes(Config.MAX_FILE_SIZE)}")
                    return redirect(url_for("index", folder=folder))
                
                data = r.content
                
                # Get filename from Content-Disposition or URL
                cd = r.headers.get('content-disposition')
                if cd:
                    fname_match = re.findall('filename=(.+)', cd)
                    if fname_match:
                        filename = secure_filename(fname_match[0].strip('"'))
                
                if not filename:
                    filename = secure_filename(url.split("/")[-1].split("?")[0]) or "downloaded_file"
                    
        except requests.RequestException as e:
            flash(f"Failed to download from URL: {str(e)}")
            return redirect(url_for("index", folder=folder))
    
    # Option 2: Upload from local file
    elif file and file.filename:
        data = file.read()
        filename = secure_filename(file.filename)
    
    else:
        flash("No file or URL provided.")
        return redirect(url_for("index", folder=folder))

    # Final size validation
    if len(data) > Config.MAX_FILE_SIZE:
        flash(f"File too large. Max size: {format_bytes(Config.MAX_FILE_SIZE)}")
        return redirect(url_for("index", folder=folder))

    # Commit to GitHub
    path = get_storage_path(filename, folder)
    timestamp = datetime.now(UTC).isoformat()
    commit_message = f"Upload {filename} @ {timestamp}"
    
    try:
        try:
            existing = repo.get_contents(path, ref=Config.GITHUB_BRANCH)
            repo.update_file(path, commit_message, data, existing.sha, branch=Config.GITHUB_BRANCH)
            flash(f"File '{filename}' updated successfully.")
        except GithubException:
            repo.create_file(path, commit_message, data, branch=Config.GITHUB_BRANCH)
            flash(f"File '{filename}' uploaded successfully.")
    except GithubException as e:
        app.logger.error(f"GitHub upload error: {e}")
        flash(f"GitHub error: {e.data.get('message', str(e))}")

    return redirect(url_for("index", folder=folder))

@app.route("/create_folder", methods=["POST"])
def create_folder():
    """Create a new folder by placing a .gitkeep file."""
    folder = request.form.get("folder", "").strip("/")
    new_folder_name = secure_filename(request.form.get("new_folder_name", "").strip())
    
    if not new_folder_name:
        flash("Folder name is required.")
        return redirect(url_for("index", folder=folder))

    new_folder_path = f"{Config.STORAGE_DIR}/{folder}/{new_folder_name}/.gitkeep".replace("//", "/")
    commit_message = f"Create folder '{new_folder_name}' @ {datetime.now(UTC).isoformat()}"
    
    try:
        repo.create_file(new_folder_path, commit_message, b"", branch=Config.GITHUB_BRANCH)
        flash(f"Folder '{new_folder_name}' created successfully.")
    except GithubException as e:
        app.logger.error(f"GitHub create folder error: {e}")
        flash(f"Failed to create folder: {e.data.get('message', str(e))}")

    return redirect(url_for("index", folder=folder))

# --- API Endpoints ---

@app.route("/api/files/<path:file_path>", methods=["GET"])
def api_get_file_info(file_path: str):
    """API endpoint to get file info."""
    try:
        c = repo.get_contents(file_path, ref=Config.GITHUB_BRANCH)
        if isinstance(c, list):
            return jsonify({"error": "Path is a directory"}), 400
            
        return jsonify({
            "name": c.name,
            "path": c.path,
            "size": c.size,
            "size_formatted": format_bytes(c.size),
            "download_url": get_direct_download_url(file_path),
            "mime_type": get_mime_type(c.name),
            "sha": c.sha
        })
    except GithubException as e:
        return jsonify({"error": e.data.get('message', str(e))}), 404

@app.route("/api/files/<path:file_path>", methods=["DELETE"])
def api_delete_file(file_path: str):
    """API endpoint to delete a file."""
    try:
        c = repo.get_contents(file_path, ref=Config.GITHUB_BRANCH)
        if isinstance(c, list):
            return jsonify({"error": "Use folder delete endpoint for directories"}), 400
            
        commit_message = f"Delete {file_path} @ {datetime.now(UTC).isoformat()}"
        repo.delete_file(file_path, commit_message, c.sha, branch=Config.GITHUB_BRANCH)
        return jsonify({"message": f"File '{file_path}' deleted successfully"})
    except GithubException as e:
        return jsonify({"error": e.data.get('message', str(e))}), 404

@app.route("/api/folders/<path:folder_path>", methods=["DELETE"])
def api_delete_folder(folder_path: str):
    """API endpoint to recursively delete a folder."""
    def recursive_delete(path):
        try:
            contents = repo.get_contents(path, ref=Config.GITHUB_BRANCH)
            if not isinstance(contents, list):
                contents = [contents]
            
            for item in contents:
                if item.type == "dir":
                    recursive_delete(item.path)
                else:
                    msg = f"Delete {item.path} @ {datetime.now(UTC).isoformat()}"
                    repo.delete_file(item.path, msg, item.sha, branch=Config.GITHUB_BRANCH)
        except GithubException:
            pass
    
    try:
        recursive_delete(folder_path)
        return jsonify({"message": f"Folder '{folder_path}' deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/folders/<path:folder_path>", methods=["GET"])
def api_list_folder(folder_path: str):
    """API endpoint to list folder contents."""
    files = list_repo_contents(folder_path)
    return jsonify({"folder": folder_path, "files": files})

# --- Error Handlers ---

@app.errorhandler(413)
def request_entity_too_large(error):
    flash(f"File too large. Maximum size is {format_bytes(Config.MAX_FILE_SIZE)}")
    return redirect(url_for("index")), 413

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", error="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template("error.html", error="Internal server error"), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)
