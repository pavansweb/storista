import os
import datetime
import requests
import mimetypes
from flask import Flask, request, jsonify, render_template, abort, redirect, url_for, flash
from github import Github, GithubException
from werkzeug.utils import secure_filename

# --- Config ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
STORAGE_DIR = "storage"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

if not (GITHUB_TOKEN and GITHUB_REPO):
    raise RuntimeError("Set GITHUB_TOKEN and GITHUB_REPO env vars before running.")

g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# --- Helpers ---
def full_path(filename, folder=""):
    """Construct full path for file in storage."""
    folder = folder.strip().strip("/")
    filename = secure_filename(filename)
    if folder:
        return f"{STORAGE_DIR}/{folder}/{filename}"
    return f"{STORAGE_DIR}/{filename}"

def get_direct_download_url(file_path):
    """Get direct GitHub raw content URL."""
    # Format: https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{file_path}"

def get_mime_type(filename):
    """Get MIME type for file."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'

def list_files(folder=""):
    """List all files and folders in given directory."""
    folder_path = f"{STORAGE_DIR}/{folder}".strip("/")
    
    try:
        contents = repo.get_contents(folder_path, ref=GITHUB_BRANCH)
        if not isinstance(contents, list):
            contents = [contents]
        
        files = []
        for c in contents:
            if c.name == ".gitkeep":
                continue
            
            item = {
                "name": c.name,
                "path": c.path,
                "is_dir": c.type == "dir",
            }
            
            if c.type == "file":
                item["size"] = c.size
                item["size_formatted"] = format_bytes(c.size)
                item["download_url"] = get_direct_download_url(c.path)
                item["mime_type"] = get_mime_type(c.name)
            
            files.append(item)
        
        # Sort: directories first, then files
        files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return files
    except GithubException:
        return []

def format_bytes(size):
    """Format bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

# --- Routes ---
@app.route("/", defaults={"folder": ""})
@app.route("/browse/<path:folder>")
def index(folder):
    """Main page displaying files and folders."""
    message = request.args.get("msg", "")
    error = request.args.get("error", "")
    files = list_files(folder)
    
    # Calculate parent folder path
    if folder:
        parts = folder.split("/")
        parent = "/".join(parts[:-1]) if len(parts) > 1 else ""
    else:
        parent = None
    
    return render_template(
        "index.html",
        files=files,
        message=message,
        error=error,
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

    # Download from URL
    if url:
        try:
            r = requests.get(url, timeout=30, stream=True)
            r.raise_for_status()
            
            # Check content length before downloading
            content_length = r.headers.get('content-length')
            if content_length and int(content_length) > MAX_FILE_SIZE:
                flash(f"File too large. Max size: {format_bytes(MAX_FILE_SIZE)}")
                return redirect(url_for("index", folder=folder))
            
            data = r.content
            
            # Try to get filename from Content-Disposition header
            if 'content-disposition' in r.headers:
                import re
                cd = r.headers['content-disposition']
                fname = re.findall('filename=(.+)', cd)
                if fname:
                    filename = secure_filename(fname[0].strip('"'))
            
            # Fallback to URL path
            if not filename:
                filename = secure_filename(url.split("/")[-1].split("?")[0])
            
            if not filename:
                filename = "downloaded_file"
                
        except requests.RequestException as e:
            flash(f"Failed to download from URL: {str(e)}")
            return redirect(url_for("index", folder=folder))
    
    # Upload from local file
    elif file and file.filename:
        data = file.read()
        filename = secure_filename(file.filename)
    
    else:
        flash("No file or URL provided.")
        return redirect(url_for("index", folder=folder))

    # Validate file size
    if len(data) > MAX_FILE_SIZE:
        flash(f"File too large. Max size: {format_bytes(MAX_FILE_SIZE)}")
        return redirect(url_for("index", folder=folder))

    # Upload to GitHub
    path = full_path(filename, folder)
    commit_message = f"Upload {filename} @ {datetime.datetime.utcnow().isoformat()}"
    
    try:
        # Check if file exists and update, otherwise create
        try:
            existing = repo.get_contents(path, ref=GITHUB_BRANCH)
            repo.update_file(
                path,
                commit_message,
                data,
                existing.sha,
                branch=GITHUB_BRANCH
            )
            msg = f"File '{filename}' updated successfully."
        except GithubException:
            repo.create_file(
                path,
                commit_message,
                data,
                branch=GITHUB_BRANCH
            )
            msg = f"File '{filename}' uploaded successfully."
        
        flash(msg)
    except GithubException as e:
        flash(f"GitHub error: {str(e)}")

    return redirect(url_for("index", folder=folder))

@app.route("/create_folder", methods=["POST"])
def create_folder():
    """Create a new folder."""
    folder = request.form.get("folder", "").strip("/")
    new_folder_name = secure_filename(request.form.get("new_folder_name", "").strip())
    
    if not new_folder_name:
        flash("Folder name is required.")
        return redirect(url_for("index", folder=folder))

    # Construct path for .gitkeep file
    if folder:
        new_folder_path = f"{STORAGE_DIR}/{folder}/{new_folder_name}/.gitkeep"
    else:
        new_folder_path = f"{STORAGE_DIR}/{new_folder_name}/.gitkeep"

    commit_message = f"Create folder '{new_folder_name}' @ {datetime.datetime.utcnow().isoformat()}"
    
    try:
        repo.create_file(
            new_folder_path,
            commit_message,
            b"",
            branch=GITHUB_BRANCH
        )
        flash(f"Folder '{new_folder_name}' created successfully.")
    except GithubException as e:
        flash(f"Failed to create folder: {str(e)}")

    return redirect(url_for("index", folder=folder))

# --- API Endpoints ---

@app.route("/api/files/<path:file_path>", methods=["GET"])
def api_get_file_info(file_path):
    """API endpoint to get file info and download URL."""
    try:
        file_content = repo.get_contents(file_path, ref=GITHUB_BRANCH)
        return jsonify({
            "name": file_content.name,
            "path": file_content.path,
            "size": file_content.size,
            "size_formatted": format_bytes(file_content.size),
            "download_url": get_direct_download_url(file_path),
            "mime_type": get_mime_type(file_content.name),
            "sha": file_content.sha
        })
    except GithubException as e:
        return jsonify({"error": str(e)}), 404

@app.route("/api/files/<path:file_path>", methods=["DELETE"])
def api_delete_file(file_path):
    """API endpoint to delete a file."""
    try:
        file_content = repo.get_contents(file_path, ref=GITHUB_BRANCH)
        commit_message = f"Delete {file_path} @ {datetime.datetime.utcnow().isoformat()}"
        repo.delete_file(
            file_path,
            commit_message,
            file_content.sha,
            branch=GITHUB_BRANCH
        )
        return jsonify({"message": f"File '{file_path}' deleted successfully"})
    except GithubException as e:
        return jsonify({"error": str(e)}), 404

@app.route("/api/folders/<path:folder_path>", methods=["DELETE"])
def api_delete_folder(folder_path):
    """API endpoint to recursively delete a folder."""
    def delete_contents(path):
        """Recursively delete folder contents."""
        try:
            contents = repo.get_contents(path, ref=GITHUB_BRANCH)
            if not isinstance(contents, list):
                contents = [contents]
            
            for item in contents:
                if item.type == "dir":
                    delete_contents(item.path)
                else:
                    commit_msg = f"Delete {item.path} @ {datetime.datetime.utcnow().isoformat()}"
                    repo.delete_file(item.path, commit_msg, item.sha, branch=GITHUB_BRANCH)
        except GithubException:
            pass
    
    try:
        delete_contents(folder_path)
        return jsonify({"message": f"Folder '{folder_path}' deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/folders/<path:folder_path>", methods=["GET"])
def api_list_folder(folder_path):
    """API endpoint to list folder contents."""
    files = list_files(folder_path)
    return jsonify({"folder": folder_path, "files": files})

# --- Error Handlers ---
@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error."""
    flash(f"File too large. Maximum size is {format_bytes(MAX_FILE_SIZE)}")
    return redirect(url_for("index")), 413

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return render_template("error.html", error="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return render_template("error.html", error="Internal server error"), 500

# --- Main ---
if __name__ == "__main__":
    app.run(debug=True, port=5001)
