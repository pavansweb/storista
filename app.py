import os
import base64
import datetime
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

def list_files():
    try:
        contents = repo.get_contents(STORAGE_DIR, ref=GITHUB_BRANCH)
        files = []
        for c in contents:
            files.append({
                "name": c.name,
                "path": c.path,
                "size": c.size,
                "download_url": url_for('download_proxy', file_path=c.path)
            })
        return files
    except GithubException:
        return []

# --- UI Route ---
@app.route("/")
def index():
    message = request.args.get("msg", "")
    return render_template("index.html", files=list_files(), message=message)

# --- Web Upload (HTML form) ---
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file uploaded.")
        return redirect(url_for("index"))

    folder = request.form.get("folder", "")
    path = full_path(file.filename, folder)
    data = file.read()

    MAX_BYTES = 50 * 1024 * 1024
    if len(data) > MAX_BYTES:
        flash("File too large.")
        return redirect(url_for("index"))

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

    return redirect(url_for("index", msg=msg))

# --- API: List files ---
@app.route("/api/files", methods=["GET"])
def api_list_files():
    return jsonify({"files": list_files()})

# --- API: Upload file ---
@app.route("/api/files", methods=["POST"])
def api_upload_file():
    file = request.files.get("file")
    folder = request.form.get("folder", "")

    if not file or file.filename == "":
        return jsonify({"error": "No file provided"}), 400

    path = full_path(file.filename, folder)
    data = file.read()

    try:
        try:
            existing = repo.get_contents(path, ref=GITHUB_BRANCH)
            repo.update_file(path, f"API upload update {path}", data, existing.sha, branch=GITHUB_BRANCH)
            return jsonify({"message": "File updated", "path": path})
        except GithubException:
            repo.create_file(path, f"API upload {path}", data, branch=GITHUB_BRANCH)
            return jsonify({"message": "File created", "path": path})
    except GithubException as e:
        return jsonify({"error": str(e)}), 500

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

# --- Proxy Download (UI use) ---
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
