"""
storista.config
~~~~~~~~~~~~~~~
Centralized configuration management for Storista.
Loads environment variables from .env and defines runtime parameters.
"""

import os
from pathlib import Path
import secrets
from typing import Optional
import warnings
from dotenv import load_dotenv

# Ensure .env is loaded if present
load_dotenv()


def _resolve_secret_key() -> str:
    """
    Resolve the Flask SECRET_KEY with strong security guarantees.
    1. Uses FLASK_SECRET or SECRET_KEY from environment if configured and non-default.
    2. Loads or generates a persistent 256-bit random key in .secret_key.
    3. Issues a prominent warning if relying on the auto-generated key.
    """
    env_secret = os.environ.get("FLASK_SECRET") or os.environ.get("SECRET_KEY")
    if env_secret and env_secret.strip() and env_secret.strip() != "dev-secret-change-me":
        return env_secret.strip()

    project_root = Path(__file__).resolve().parent.parent
    secret_file = project_root / ".secret_key"

    if secret_file.is_file():
        try:
            stored = secret_file.read_text(encoding="utf-8").strip()
            if stored and len(stored) >= 32:
                return stored
        except Exception:
            pass

    generated = secrets.token_hex(32)
    try:
        secret_file.write_text(generated, encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except OSError:
            pass
        warnings.warn(
            "Neither FLASK_SECRET nor SECRET_KEY was configured in .env. "
            f"Generated a persistent random 256-bit secret key in {secret_file}. "
            "For production deployments, define SECRET_KEY in your .env file.",
            UserWarning,
            stacklevel=2,
        )
    except Exception:
        warnings.warn(
            "Neither FLASK_SECRET nor SECRET_KEY was configured in .env. "
            "Generated an ephemeral in-memory random secret key. "
            "For production deployments, define SECRET_KEY in your .env file.",
            UserWarning,
            stacklevel=2,
        )

    return generated


class Config:
    """Default application configuration loaded from environment variables."""

    # GitHub Credentials & Repository Target
    GIT_TOKEN: Optional[str] = os.environ.get("GIT_TOKEN")
    GIT_REPO: Optional[str] = os.environ.get("GIT_REPO")
    GITHUB_BRANCH: str = os.environ.get("GITHUB_BRANCH", "main")

    # Storage Sandboxing & Limits
    STORAGE_DIR: str = os.environ.get("STORAGE_DIR", "storage")
    MAX_FILE_SIZE: int = int(os.environ.get("MAX_FILE_SIZE", 50 * 1024 * 1024))  # 50MB default

    # Security & Sessions
    SECRET_KEY: str = _resolve_secret_key()
    VAULT_PASSWORD: str = os.environ.get("VAULT_PASSWORD", "cheese burger")

    # Performance & In-Memory Caching
    CACHE_TTL: int = int(os.environ.get("CACHE_TTL", 60))  # 60 seconds
    CACHE_MAXSIZE: int = int(os.environ.get("CACHE_MAXSIZE", 200))

    # Testing flag
    TESTING: bool = False

    @classmethod
    def validate(cls) -> None:
        """
        Validate that critical production configuration variables are set.
        Raises RuntimeError if required variables are missing.
        """
        missing = []
        if not cls.GIT_TOKEN:
            missing.append("GIT_TOKEN")
        if not cls.GIT_REPO:
            missing.append("GIT_REPO")

        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Please configure them in .env before running the application."
            )

        raw_secret = os.environ.get("FLASK_SECRET") or os.environ.get("SECRET_KEY")
        if not raw_secret or raw_secret.strip() == "dev-secret-change-me":
            warnings.warn(
                "Running with auto-generated SECRET_KEY. Sessions will invalidate if the key is removed. "
                "Set SECRET_KEY in .env for production stability.",
                UserWarning,
                stacklevel=2,
            )
