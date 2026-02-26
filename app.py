import os
import datetime
import requests
import mimetypes
from flask import Flask, request, jsonify, render_template, abort, redirect, url_for, flash
from github import Github, GithubException
from supabase import create_client, Client
from werkzeug.utils import secure_filename

# --- Config ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "storage")

STORAGE_DIR = ""
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

if not (GITHUB_TOKEN and GITHUB_REPO):
    raise RuntimeError("Set GITHUB_TOKEN and GITHUB_REPO env vars.")

if not (SUPABASE_URL and SUPABASE_KEY):
    raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars.")

# GitHub setup
g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

# Supabase setup
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


# --- Helpers ---
def full_path(filename, folder=""):
    folder = folder.strip().strip("/")
    filename = secure_filename(filename)

    if folder:
        return f"{folder}/{filename}"
    return filename


def get_direct_download_url(file_path):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{file_path}"


def get_mime_type(filename):
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'


def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


# --- Combined File Listing ---
def list_files(folder=""):
    files = []

    # --------------------------
    # 1️⃣ GitHub Files
    # --------------------------
    github_folder_path = f"{STORAGE_DIR}/{folder}".strip("/")

    try:
        contents = repo.get_contents(github_folder_path, ref=GITHUB_BRANCH)
        if not isinstance(contents, list):
            contents = [contents]

        for c in contents:
            if c.name == ".gitkeep":
                continue

            item = {
                "name": c.name,
                "path": c.path,
                "is_dir": c.type == "dir",
                "source": "github"
            }

            if c.type == "file":
                item["size"] = c.size
                item["size_formatted"] = format_bytes(c.size)
                item["download_url"] = get_direct_download_url(c.path)
                item["mime_type"] = get_mime_type(c.name)

            files.append(item)

    except GithubException:
        pass

    # --------------------------
    # 2️⃣ Supabase Files
    # --------------------------
    try:
        supabase_folder_path = folder.strip("/")
    
        response = supabase.storage.from_(SUPABASE_BUCKET).list(
            supabase_folder_path
        )
    
        sb_items = response.data if hasattr(response, "data") else response
    
        print("Supabase items:", sb_items)  # DEBUG
    
        for item in sb_items:
            if item["name"].startswith("."):
                continue
    
            is_dir = item.get("metadata") is None
    
            file_path = (
                f"{supabase_folder_path}/{item['name']}".strip("/")
                if supabase_folder_path
                else item["name"]
            )
    
            file_info = {
                "name": item["name"],
                "path": file_path,
                "is_dir": is_dir,
                "source": "supabase"
            }
    
            if not is_dir:
                size = item["metadata"]["size"]
    
                public_url = supabase.storage.from_(SUPABASE_BUCKET)\
                    .get_public_url(file_path)
    
                file_info["size"] = size
                file_info["size_formatted"] = format_bytes(size)
                file_info["download_url"] = public_url["publicURL"]
                file_info["mime_type"] = get_mime_type(item["name"])
    
            files.append(file_info)
    
    except Exception as e:
        print("Supabase list error:", e)

    unique = {}
    for f in files:
        unique[(f["name"], f["is_dir"])] = f

    files = list(unique.values())

    files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return files


# --- Routes ---
@app.route("/", defaults={"folder": ""})
@app.route("/browse/<path:folder>")
def index(folder):
    files = list_files(folder)

    if folder:
        parts = folder.split("/")
        parent = "/".join(parts[:-1]) if len(parts) > 1 else ""
    else:
        parent = None

    return render_template(
        "index.html",
        files=files,
        current_folder=folder,
        parent_folder=parent
    )


@app.route("/upload", methods=["POST"])
def upload():
    folder = request.form.get("folder", "").strip("/")
    file = request.files.get("file")

    if not file or not file.filename:
        flash("No file provided.")
        return redirect(url_for("index", folder=folder))

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        flash(f"File too large. Max size: {format_bytes(MAX_FILE_SIZE)}")
        return redirect(url_for("index", folder=folder))

    filename = secure_filename(file.filename)
    path = full_path(filename, folder)

    try:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            path,
            data,
            {"content-type": get_mime_type(filename)}
        )

        flash(f"File '{filename}' uploaded to Supabase successfully.")

    except Exception as e:
        flash(f"Supabase error: {str(e)}")

    return redirect(url_for("index", folder=folder))


# --- Delete File (Both Sources Supported) ---
@app.route("/api/files/<path:file_path>", methods=["DELETE"])
def api_delete_file(file_path):
    try:
        # Try GitHub delete
        try:
            file_content = repo.get_contents(file_path, ref=GITHUB_BRANCH)
            repo.delete_file(
                file_path,
                f"Delete {file_path}",
                file_content.sha,
                branch=GITHUB_BRANCH
            )
            return jsonify({"message": "Deleted from GitHub"})
        except GithubException:
            pass

        # Try Supabase delete
        supabase.storage.from_(SUPABASE_BUCKET).remove([file_path])
        return jsonify({"message": "Deleted from Supabase"})

    except Exception as e:
        return jsonify({"error": str(e)}), 404


# --- Error Handler ---
@app.errorhandler(413)
def request_entity_too_large(error):
    flash(f"File too large. Maximum size is {format_bytes(MAX_FILE_SIZE)}")
    return redirect(url_for("index")), 413


if __name__ == "__main__":
    app.run(debug=True, port=5001)
