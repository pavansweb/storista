"""
storista
~~~~~~~~
Storista cloud file storage application package.
Provides the application factory create_app() and core initialization.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash

from storista.config import Config
from storista.services.github_service import GitHubService


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    """
    Application factory for Storista.

    Args:
        test_config: Optional dictionary of configuration overrides for testing.

    Returns:
        Configured Flask application instance.
    """
    # 1. Determine filesystem paths relative to package root
    package_dir = Path(__file__).resolve().parent
    project_root = package_dir.parent
    template_folder = str(project_root / "templates")
    static_folder = str(project_root / "static")

    # 2. Instantiate Flask with explicit template and static folder roots
    app = Flask(
        __name__,
        template_folder=template_folder,
        static_folder=static_folder,
        static_url_path="/static"
    )

    # 3. Load Configuration
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    app.secret_key = app.config.get("SECRET_KEY", "dev-secret-change-me")
    app.config["MAX_CONTENT_LENGTH"] = app.config.get("MAX_FILE_SIZE", 50 * 1024 * 1024)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    # 4. Service Dependency Injection
    if test_config and "GITHUB_SERVICE" in test_config:
        service = test_config["GITHUB_SERVICE"]
    else:
        if not app.config.get("TESTING"):
            Config.validate()

        service = GitHubService(
            token=app.config.get("GIT_TOKEN", "") or "",
            repo=app.config.get("GIT_REPO", "") or "",
            branch=app.config.get("GITHUB_BRANCH", "main"),
            storage_dir=app.config.get("STORAGE_DIR", "storage"),
            cache_ttl=app.config.get("CACHE_TTL", 60),
            cache_maxsize=app.config.get("CACHE_MAXSIZE", 200),
        )

    app.extensions["github_service"] = service
    app.github_service = service

    # 5. Legacy URL Resolution Handler
    # Ensures templates calling `url_for('index', ...)` continue working seamlessly
    # without needing immediate modifications in Milestone 1.
    def handle_url_build_error(error, endpoint, values):
        if "." not in endpoint and f"web.{endpoint}" in app.view_functions:
            return url_for(f"web.{endpoint}", **values)
        return None

    app.url_build_error_handlers.append(handle_url_build_error)

    # 6. Global Error Handlers (with API content negotiation)
    def is_api_or_json_request() -> bool:
        """Helper to determine if request expects JSON vs HTML response."""
        if request.path.startswith("/api/"):
            return True
        if request.is_json:
            return True
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        best = request.accept_mimetypes.best_match(["application/json", "text/html"])
        return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]

    @app.errorhandler(PermissionError)
    def handle_permission_error(error):
        msg = str(error) or "Access denied"
        if is_api_or_json_request():
            return jsonify({"error": msg}), 403
        return render_template("error.html", error=msg), 403

    @app.errorhandler(FileNotFoundError)
    def handle_file_not_found(error):
        msg = str(error) or "Resource not found"
        if is_api_or_json_request():
            return jsonify({"error": msg}), 404
        return render_template("error.html", error=msg), 404

    @app.errorhandler(IsADirectoryError)
    def handle_is_a_directory(error):
        msg = str(error) or "Path is a directory"
        if is_api_or_json_request():
            return jsonify({"error": msg}), 400
        return render_template("error.html", error=msg), 400

    @app.errorhandler(FileExistsError)
    def handle_file_exists(error):
        msg = str(error) or "Resource already exists"
        if is_api_or_json_request():
            return jsonify({"error": msg}), 409
        return render_template("error.html", error=msg), 409

    @app.errorhandler(ValueError)
    def handle_value_error(error):
        msg = str(error) or "Invalid input"
        if is_api_or_json_request():
            return jsonify({"error": msg}), 400
        return render_template("error.html", error=msg), 400

    @app.errorhandler(400)
    def bad_request(error):
        desc = getattr(error, "description", "Bad request")
        if is_api_or_json_request():
            return jsonify({"error": str(desc)}), 400
        return render_template("error.html", error=str(desc)), 400

    @app.errorhandler(403)
    def forbidden(error):
        desc = getattr(error, "description", "Access denied")
        if is_api_or_json_request():
            return jsonify({"error": str(desc)}), 403
        return render_template("error.html", error=str(desc)), 403

    @app.errorhandler(404)
    def not_found(error):
        desc = getattr(error, "description", "Page not found")
        if is_api_or_json_request():
            return jsonify({"error": str(desc)}), 404
        return render_template("error.html", error=str(desc)), 404

    @app.errorhandler(413)
    def request_entity_too_large(error):
        max_size_formatted = service.format_bytes(app.config["MAX_CONTENT_LENGTH"])
        if is_api_or_json_request():
            return jsonify({"error": f"File too large. Maximum size is {max_size_formatted}"}), 413
        flash(f"File too large. Maximum size is {max_size_formatted}")
        return redirect(url_for("web.index")), 413

    @app.errorhandler(500)
    def internal_error(error):
        desc = getattr(error, "description", "Internal server error")
        if is_api_or_json_request():
            return jsonify({"error": str(desc)}), 500
        return render_template("error.html", error="Internal server error"), 500

    # 7. Register Blueprints
    from storista.routes.web import web_bp
    from storista.routes.api import api_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    return app


__all__ = ["create_app", "Config"]
