import os
import base64
import datetime
import requests
from io import BytesIO
from flask import Flask, request, jsonify, render_template, send_file, abort, redirect, url_for, flash
from github import Github, GithubException
from werkzeug.utils import secure_filename

# --- Config ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
STORAGE_DIR = "storage"

if not (GITHUB_TOKEN and GITHUB_REPO):
    raise RuntimeError("Set GITHUB_TOKEN and GITHUB_REPO env vars before running.")

g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# --- Helpers ---
def full_path(filename, folder=""):
    folder = folder.strip().strip("/")
    filename = secure_filename(filename)
    if folder:
        return f"{STORAGE_DIR}/{folder}/{filename}"
    return f"{STORAGE_DIR}/{filename}"

def list_files(folder=""):
    folder_path = f"{STORAGE_DIR}/{folder}".strip("/")
    
    try:
        contents = repo.get_contents(folder_path, ref=GITHUB_BRANCH)
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
                item["download_url"] = url_for('download_proxy', file_path=c.path)
            files.append(item)
        return files
    except GithubException:
        return []

# --- Routes ---
@app.route("/", defaults={"folder": ""})
@app.route("/browse/<path:folder>")
def index(folder):
    message = request.args.get("msg", "")
    files = list_files(folder)
    parent = "/".join(folder.split("/")[:-1])
    return render_template("index.html", files=files, message=message, current_folder=folder, parent_folder=parent)

@app.route("/upload", methods=["POST"])
def upload():
    folder = request.form.get("folder", "").strip("/")
    url = request.form.get("url", "").strip()
    file = request.files.get("file")
    data = None
    filename = None

    if url:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.content
            filename = secure_filename(url.split("/")[-1])
        except Exception as e:
            flash(f"Failed to download: {e}")
            return redirect(url_for("index", folder=folder))
    elif file and file.filename:
        data = file.read()
        filename = secure_filename(file.filename)
    else:
        flash("No file or URL provided.")
        return redirect(url_for("index", folder=folder))

    path = full_path(filename, folder)
    MAX_BYTES = 50 * 1024 * 1024
    if len(data) > MAX_BYTES:
        flash("File too large.")
        return redirect(url_for("index", folder=folder))

    commit_message = f"Upload {path} @ {datetime.datetime.utcnow().isoformat()}"
    try:
        try:
            existing = repo.get_contents(path, ref=GITHUB_BRANCH)
            repo.update_file(path, commit_message, data, existing.sha, branch=GITHUB_BRANCH)
            msg = "File updated."
        except GithubException:
            repo.create_file(path, commit_message, data, branch=GITHUB_BRANCH)
            msg = "File uploaded."
    except GithubException as e:
        msg = f"GitHub error: {e}"

    return redirect(url_for("index", folder=folder, msg=msg))

@app.route("/create_folder", methods=["POST"])
def create_folder():
    folder = request.form.get("folder", "").strip("/")
    new_folder_name = request.form.get("new_folder_name", "").strip()
    if not new_folder_name:
        flash("Folder name required.")
        return redirect(url_for("index", folder=folder))

    if folder:
        new_folder_path = f"{STORAGE_DIR}/{folder}/{new_folder_name}/.gitkeep"
    else:
        new_folder_path = f"{STORAGE_DIR}/{new_folder_name}/.gitkeep"

    print("FOLDER:",folder)
    print("NEW FOLDER PATH:",new_folder_path)
    commit_message = f"Create folder {new_folder_name} @ {datetime.datetime.utcnow().isoformat()}"
    try:
        repo.create_file(new_folder_path, commit_message, b"", branch=GITHUB_BRANCH)
        msg = f"Folder '{new_folder_name}' created."
    except GithubException as e:
        msg = f"GitHub error: {e}"

    return redirect(url_for("index", folder=folder, msg=msg))

# --- API: Delete folder (recursive) ---
@app.route("/api/folders/<path:folder_path>", methods=["DELETE"])
def api_delete_folder(folder_path):
    try:
        contents = repo.get_contents(folder_path, ref=GITHUB_BRANCH)
        for item in contents:
            if item.type == "dir":
                # recursive delete for nested folders
                api_delete_folder(item.path)
            else:
                repo.delete_file(item.path, f"Deleted {item.path}", item.sha, branch=GITHUB_BRANCH)

        # delete marker file (like .gitkeep) if exists
        try:
            folder_marker = repo.get_contents(f"{folder_path}/.gitkeep", ref=GITHUB_BRANCH)
            repo.delete_file(folder_marker.path, f"Deleted folder marker {folder_marker.path}", folder_marker.sha, branch=GITHUB_BRANCH)
        except GithubException:
            pass

        return jsonify({"message": f"Folder '{folder_path}' deleted"})
    except GithubException:
        return jsonify({"error": "Folder not found"}), 404


# --- API: Download file ---
@app.route("/api/files/<path:file_path>", methods=["GET"])
def api_download_file(file_path):
    try:
        file_content = repo.get_contents(file_path, ref=GITHUB_BRANCH)
        raw = base64.b64decode(file_content.content)
        return send_file(BytesIO(raw), download_name=file_content.name, as_attachment=True)
    except GithubException:
        return jsonify({"error": "File not found"}), 404

# --- API: Delete file ---
@app.route("/api/files/<path:file_path>", methods=["DELETE"])
def api_delete_file(file_path):
    try:
        file_content = repo.get_contents(file_path, ref=GITHUB_BRANCH)
        repo.delete_file(file_path, f"Deleted {file_path}", file_content.sha, branch=GITHUB_BRANCH)
        return jsonify({"message": f"{file_path} deleted"})
    except GithubException:
        return jsonify({"error": "File not found"}), 404

# --- Proxy Download (for UI) ---
@app.route("/download_proxy/<path:file_path>")
def download_proxy(file_path):
    try:
        file_content = repo.get_contents(file_path, ref=GITHUB_BRANCH)
    except GithubException:
        abort(404)
    raw = base64.b64decode(file_content.content)
    return send_file(BytesIO(raw), download_name=file_content.name, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
