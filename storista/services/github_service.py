"""
storista.services.github_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GitHub storage service for Storista.
Encapsulates PyGithub operations, strict storage sandboxing, in-memory TTL
caching, SSRF-safe remote URL downloads, and authenticated streaming downloads.
"""

import ipaddress
import json
import mimetypes
import os
import posixpath
import re
import socket
import threading
import urllib.parse
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any, Tuple, Generator

import requests
from cachetools import TTLCache
from flask import current_app
from github import Github, Auth, GithubException
from werkzeug.utils import secure_filename


# ==============================================================================
# Storage Sandboxing & Path Helpers
# ==============================================================================

def normalize_storage_path(path: Optional[str]) -> str:
    """
    Normalizes an input path to a canonical repository path within 'storage/'.

    Accepts:
      - Bare paths: 'Photo-1.jpeg' -> 'storage/Photo-1.jpeg'
      - Prefixed paths: 'storage/Photo-1.jpeg' -> 'storage/Photo-1.jpeg'
      - Bare folder paths: 'vault' -> 'storage/vault'
      - Prefixed folder paths: 'storage/vault' -> 'storage/vault'
      - Root folder: '' or 'storage' or 'storage/' -> 'storage'

    Rejects (raises PermissionError -> HTTP 403 Forbidden):
      - Traversal segments: '..', '../app.py', 'storage/../app.py', '%2e%2e/app.py'
      - Absolute paths / leading slashes: '/app.py', '/storage/Photo-1.jpeg', '//etc/passwd'
      - Backslashes: 'storage\\app.py'
      - Null bytes or control characters

    Returns:
      Canonical repository path starting with 'storage' (e.g. 'storage', 'storage/file.txt').
    """
    if path is None:
        path = ""

    # Step 1: Decode URL percent-encoding (e.g. %2e%2e -> ..) and normalize unicode dots
    unquoted = urllib.parse.unquote(str(path)).strip()
    for dot_char in ("\uFF0E", "\u2024", "\u3002"):
        unquoted = unquoted.replace(dot_char, ".")
    unquoted = unquoted.replace("\u2025", "..")

    # Step 2: Reject null bytes, leading slashes, and backslashes
    if "\x00" in unquoted:
        raise PermissionError(f"Access denied: null byte in path {path!r}")
    if unquoted.startswith("/") or "\\" in unquoted:
        raise PermissionError(f"Access denied: absolute path or backslash separator in {path!r}")

    # Step 3: Check for directory traversal in raw components before posixpath.normpath
    clean = unquoted.strip("/")
    raw_segments = clean.split("/") if clean else []
    for seg in raw_segments:
        if seg == ".." or seg.startswith("../") or seg == ".":
            if seg == "." and len(raw_segments) == 1:
                continue  # Single '.' is acceptable as current folder
            raise PermissionError(f"Access denied: directory traversal in {path!r}")

    # Step 4: POSIX path normalization
    norm = posixpath.normpath(clean) if clean else ""
    norm_segments = norm.split("/") if norm else []
    if ".." in norm_segments or norm.startswith(".."):
        raise PermissionError(f"Access denied: directory traversal in {path!r}")

    # Step 5: Extract storage-relative path
    if norm == "storage" or norm == "." or norm == "":
        rel_path = ""
    elif norm.startswith("storage/"):
        rel_path = norm[len("storage/"):]
    else:
        rel_path = norm

    # Step 6: Defensive re-validation of relative path
    if rel_path.startswith("..") or "/../" in f"/{rel_path}/":
        raise PermissionError(f"Access denied: path traversal in {path!r}")

    # Step 7: Construct canonical storage path
    if not rel_path:
        return "storage"
    return f"storage/{rel_path}"


def get_display_path(normalized_path: str) -> str:
    """
    Strips the leading 'storage/' prefix from a normalized repository path
    for UI rendering, breadcrumb navigation, and user-facing parameters.

    Examples:
      'storage' -> ''
      'storage/Photo-1.jpeg' -> 'Photo-1.jpeg'
      'storage/vault' -> 'vault'
      'storage/vault/subfolder' -> 'vault/subfolder'
    """
    if not normalized_path or normalized_path == "storage":
        return ""
    if normalized_path.startswith("storage/"):
        return normalized_path[len("storage/"):]
    return normalized_path


def get_parent_folder(normalized_path: str) -> Optional[str]:
    """
    Computes the parent folder display path for navigation breadcrumbs.
    Returns None if the path is the root storage folder ('storage').
    """
    display = get_display_path(normalized_path)
    if not display:
        return None
    parts = display.strip("/").split("/")
    if len(parts) <= 1:
        return ""
    return "/".join(parts[:-1])


def is_vault_path(path: Optional[str]) -> bool:
    """
    Determines if a given path is the vault directory or resides within it.
    Accurately handles both bare ('vault') and prefixed ('storage/vault') paths.
    Case-insensitive, handles redundant slashes, and safely rejects None/empty values.
    Prevents false positives on 'vault_notes' or 'vault-public'.
    """
    if not path or not isinstance(path, str):
        return False
    segments = [seg for seg in path.strip().strip("/").split("/") if seg and seg != "."]
    if not segments:
        return False
    if segments[0].lower() == "storage":
        segments = segments[1:]
    if not segments:
        return False
    return segments[0].lower() == "vault"


# ==============================================================================
# Error Extraction & Filename Sanitization
# ==============================================================================

def extract_github_error_message(e: GithubException, default_message: str = "GitHub API error") -> str:
    """
    Safely extract a human-readable error message from a GithubException.
    Guarantees no TypeError, AttributeError, or empty-string return across all
    GitHub API error shapes and data payloads.
    """
    data = getattr(e, "data", None)

    # Step 1: Decode stringified JSON responses (common from streaming API fallbacks)
    if isinstance(data, str) and data.strip().startswith(("{", "[")):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, (dict, list)):
                data = parsed
        except Exception:
            pass

    # Step 2: Extract from dictionary payload
    if isinstance(data, dict):
        main_msg = ""
        raw_msg = data.get("message")
        if raw_msg is not None:
            cleaned = " ".join(str(raw_msg).split())
            if cleaned and cleaned.lower() != "none":
                main_msg = cleaned

        if not main_msg:
            raw_err = data.get("error")
            raw_desc = data.get("error_description")
            if raw_err and raw_desc:
                main_msg = f"{str(raw_err).strip()}: {str(raw_desc).strip()}"
            elif raw_desc:
                main_msg = str(raw_desc).strip()
            elif raw_err:
                main_msg = str(raw_err).strip()

        details = []
        raw_errors = data.get("errors")
        if isinstance(raw_errors, list):
            for item in raw_errors:
                if isinstance(item, dict):
                    item_msg = item.get("message")
                    if item_msg is not None:
                        item_clean = " ".join(str(item_msg).split())
                        if item_clean and item_clean.lower() != "none":
                            details.append(item_clean)
                            continue
                    field = item.get("field")
                    code = item.get("code")
                    if field and code:
                        details.append(f"{field} ({code})")
                    elif code:
                        details.append(str(code).strip())
                    elif field:
                        details.append(str(field).strip())
                elif isinstance(item, str):
                    item_clean = " ".join(item.split())
                    if item_clean:
                        details.append(item_clean)
                elif item is not None:
                    item_clean = " ".join(str(item).split())
                    if item_clean and item_clean.lower() != "none":
                        details.append(item_clean)
        elif isinstance(raw_errors, str):
            clean_errors = " ".join(raw_errors.split())
            if clean_errors:
                details.append(clean_errors)

        if main_msg and details:
            return f"{main_msg}: {'; '.join(details)}"
        elif main_msg:
            return main_msg
        elif details:
            return "; ".join(details)

    # Step 3: Handle plain string responses
    elif isinstance(data, str) and data.strip():
        cleaned = " ".join(data.split())
        if cleaned.lower().startswith(("<html", "<!doctype")):
            if hasattr(e, "status") and e.status:
                return f"{default_message} (HTTP {e.status})"
        else:
            return cleaned

    # Step 4: Fallback to status code or string representation
    if hasattr(e, "status") and e.status:
        return f"{default_message} (HTTP {e.status})"

    err_str = str(e).strip()
    if err_str and err_str.lower() != "none":
        return err_str
    return default_message


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename using secure_filename with a timestamped fallback.
    If secure_filename strips all characters or the base name, supplies
    a timestamped fallback name 'upload_YYYYMMDD_HHMMSS' (with extension if safe).
    """
    if not filename:
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"upload_{timestamp_str}"

    base, ext = os.path.splitext(filename)
    safe_base = secure_filename(base)
    safe_ext = secure_filename(ext.lstrip("."))

    if not safe_base:
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        if safe_ext:
            return f"upload_{timestamp_str}.{safe_ext}"
        return f"upload_{timestamp_str}"

    if safe_ext:
        return f"{safe_base}.{safe_ext}"
    return safe_base


# ==============================================================================
# Thread-Safe In-Memory Directory Cache
# ==============================================================================

class DirectoryCache:
    """
    Thread-safe in-memory TTL cache for GitHub directory listings.
    """
    def __init__(self, maxsize: int = 200, ttl: int = 60):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()

    def get(self, normalized_folder: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached folder contents if not expired."""
        with self._lock:
            val = self._cache.get(normalized_folder)
            return [dict(item) for item in val] if val is not None else None

    def set(self, normalized_folder: str, items: List[Dict[str, Any]]) -> None:
        """Store folder contents in cache."""
        with self._lock:
            self._cache[normalized_folder] = [dict(item) for item in items]

    def invalidate(self, normalized_folder: str) -> None:
        """Invalidate a specific folder cache entry."""
        with self._lock:
            self._cache.pop(normalized_folder, None)

    def invalidate_folder_and_relations(self, normalized_folder: str) -> None:
        """
        Invalidate a folder, its parent folder, and any descendant folders.
        Used on folder creation and folder deletion.
        """
        with self._lock:
            # 1. Invalidate folder itself
            self._cache.pop(normalized_folder, None)

            # 2. Invalidate parent folder
            if "/" in normalized_folder:
                parent = normalized_folder.rsplit("/", 1)[0]
                self._cache.pop(parent, None)
            elif normalized_folder != "storage":
                self._cache.pop("storage", None)

            # 3. Invalidate descendant folders
            prefix = f"{normalized_folder}/"
            descendant_keys = [k for k in list(self._cache.keys()) if k.startswith(prefix)]
            for k in descendant_keys:
                self._cache.pop(k, None)

    def clear(self) -> None:
        """Flush the entire cache."""
        with self._lock:
            self._cache.clear()


# ==============================================================================
# SSRF Validation & Safe URL Download
# ==============================================================================

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),          # RFC 1918 Private
    ipaddress.ip_network("100.64.0.0/10"),       # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),         # Loopback
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local / Cloud metadata (AWS/Azure/GCP)
    ipaddress.ip_network("172.16.0.0/12"),       # RFC 1918 Private
    ipaddress.ip_network("192.0.0.0/24"),        # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),        # TEST-NET-1 Documentation
    ipaddress.ip_network("192.168.0.0/16"),      # RFC 1918 Private
    ipaddress.ip_network("198.18.0.0/15"),       # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),     # TEST-NET-2 Documentation
    ipaddress.ip_network("203.0.113.0/24"),      # TEST-NET-3 Documentation
    ipaddress.ip_network("224.0.0.0/4"),         # Multicast
    ipaddress.ip_network("240.0.0.0/4"),         # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6 Networks
    ipaddress.ip_network("::1/128"),             # Loopback
    ipaddress.ip_network("::/128"),              # Unspecified
    ipaddress.ip_network("fc00::/7"),            # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),           # Link-local
    ipaddress.ip_network("ff00::/8"),            # Multicast
]


def validate_url_for_ssrf(url: str) -> None:
    """
    Validates that a URL uses HTTP/HTTPS and resolves strictly to public,
    non-private, non-loopback IP addresses.

    Raises:
      ValueError if scheme is invalid or resolved IP is private/internal.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    parsed = urllib.parse.urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL does not contain a valid hostname.")

    port = parsed.port or (443 if scheme == "https" else 80)

    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve hostname '{hostname}': {e}") from e

    if not addr_infos:
        raise ValueError(f"Hostname '{hostname}' did not resolve to any IP address.")

    for family, socktype, proto, canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f"Invalid IP address format resolved: {ip_str}")

        if (ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or
                ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_unspecified):
            raise ValueError(f"Access to private/internal IP address {ip_str} is forbidden.")

        for blocked_net in BLOCKED_IP_NETWORKS:
            if ip_obj in blocked_net:
                raise ValueError(f"Access to restricted network address {ip_str} is forbidden.")


def extract_filename_from_response(url: str, headers: Dict[str, str]) -> str:
    """
    Extracts and sanitizes filename from Content-Disposition header or URL path.
    Supplies timestamped fallback with guessed extension if sanitized name is empty.
    """
    filename = None
    cd = headers.get("content-disposition", "") or headers.get("Content-Disposition", "")
    if cd:
        m_star = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.IGNORECASE)
        if m_star:
            filename = urllib.parse.unquote(m_star.group(1).strip("\"' "))
        else:
            m = re.search(r"filename=[\"']?([^;\"']+)[\"']?", cd, re.IGNORECASE)
            if m:
                filename = m.group(1).strip("\"' ")

    if not filename:
        parsed = urllib.parse.urlsplit(url)
        path_name = parsed.path.rstrip("/").split("/")[-1]
        if path_name:
            filename = urllib.parse.unquote(path_name)

    safe_name = sanitize_filename(filename) if filename else ""

    if not safe_name:
        ext = ""
        ct = headers.get("content-type", "") or headers.get("Content-Type", "")
        ct_clean = ct.split(";")[0].strip()
        if ct_clean:
            ext = mimetypes.guess_extension(ct_clean) or ""
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_name = f"upload_{ts}{ext}"

    return safe_name


def safe_download_from_url(url: str, max_size: int, max_redirects: int = 3) -> Tuple[str, bytes]:
    """
    Downloads remote file with complete SSRF validation, safe redirect tracking,
    and bounded chunk streaming up to max_size.

    Returns:
      (sanitized_filename, file_data_bytes)

    Raises:
      ValueError if URL is invalid, target is private IP, redirects exceeded,
      or payload exceeds max_size.
    """
    current_url = url.strip()
    session = requests.Session()

    for hop in range(max_redirects + 1):
        validate_url_for_ssrf(current_url)

        try:
            resp = session.get(current_url, stream=True, allow_redirects=False, timeout=15)
        except requests.RequestException as e:
            raise ValueError(f"HTTP connection failed: {e}") from e

        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                resp.close()
                raise ValueError("Redirect response missing Location header.")
            current_url = urllib.parse.urljoin(current_url, location)
            resp.close()
            continue

        if resp.status_code != 200:
            resp.close()
            raise ValueError(f"Remote server returned HTTP {resp.status_code}.")

        cl = resp.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > max_size:
            resp.close()
            raise ValueError(f"File exceeds maximum size limit ({max_size} bytes).")

        chunks = []
        total_bytes = 0
        try:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > max_size:
                    resp.close()
                    raise ValueError(f"File size exceeds maximum limit of {max_size} bytes.")
                chunks.append(chunk)
        finally:
            resp.close()

        data = b"".join(chunks)
        filename = extract_filename_from_response(current_url, dict(resp.headers))
        return filename, data

    raise ValueError(f"Exceeded maximum redirect limit of {max_redirects}.")


# ==============================================================================
# GitHubService Class
# ==============================================================================

class GitHubService:
    """
    High-level interface to GitHub repository storage.
    Enforces path sandboxing inside storage/, provides directory caching,
    safe error extraction, and streaming downloads.
    """

    def __init__(
        self,
        token: str,
        repo: str,
        branch: str = "main",
        storage_dir: str = "storage",
        cache_ttl: int = 60,
        cache_maxsize: int = 200,
    ):
        self.token = token
        self.repo_name = repo
        self.branch = branch
        self.storage_dir = storage_dir
        self.cache = DirectoryCache(maxsize=cache_maxsize, ttl=cache_ttl)

        self._client: Optional[Github] = None
        self._repo = None

    @property
    def client(self) -> Github:
        """Lazily initialize authenticated PyGithub client using modern Auth.Token."""
        if self._client is None:
            if not self.token:
                raise ValueError("GitHub token is not configured")
            auth = Auth.Token(self.token)
            self._client = Github(auth=auth)
        return self._client

    @property
    def repo(self):
        """Lazily retrieve PyGithub Repository object."""
        if self._repo is None:
            if not self.repo_name:
                raise ValueError("GitHub repository name is not configured")
            self._repo = self.client.get_repo(self.repo_name)
        return self._repo

    # --- Path Helpers (Exposed as methods for convenience) ---

    @staticmethod
    def normalize_storage_path(path: Optional[str]) -> str:
        return normalize_storage_path(path)

    @staticmethod
    def get_display_path(normalized_path: str) -> str:
        return get_display_path(normalized_path)

    @staticmethod
    def get_parent_folder(normalized_path: str) -> Optional[str]:
        return get_parent_folder(normalized_path)

    @staticmethod
    def is_vault_path(path: str) -> bool:
        return is_vault_path(path)

    @staticmethod
    def get_safe_error_message(e: GithubException) -> str:
        return extract_github_error_message(e)

    @staticmethod
    def format_bytes(size: int) -> str:
        """Format bytes to human readable format."""
        s = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if s < 1024.0:
                return f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} PB"

    @staticmethod
    def get_mime_type(filename: str) -> str:
        """Get MIME type for filename."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def get_direct_download_url(self, file_path: str) -> str:
        """Get direct raw GitHub content URL for normalized path."""
        norm_path = self.normalize_storage_path(file_path)
        return f"https://raw.githubusercontent.com/{self.repo_name}/{self.branch}/{norm_path}"

    # --- Core File & Directory Operations ---

    def list_contents(self, folder: str = "", use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        List all files and folders in given storage directory.
        Checks TTL cache first if use_cache is True.
        """
        norm_folder = self.normalize_storage_path(folder)

        if use_cache:
            cached = self.cache.get(norm_folder)
            if cached is not None:
                return cached

        try:
            contents = self.repo.get_contents(norm_folder, ref=self.branch)
            if not isinstance(contents, list):
                contents = [contents]

            items = []
            for c in contents:
                if c.name == ".gitkeep":
                    continue

                item: Dict[str, Any] = {
                    "name": c.name,
                    "path": c.path,
                    "is_dir": c.type == "dir",
                }

                if c.type == "file":
                    item.update({
                        "size": c.size,
                        "size_formatted": self.format_bytes(c.size),
                        "download_url": self.get_direct_download_url(c.path),
                        "mime_type": self.get_mime_type(c.name),
                    })

                items.append(item)

            # Sort: directories first, then files alphabetically (case-insensitive)
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

            if use_cache:
                self.cache.set(norm_folder, items)

            return items

        except GithubException as e:
            if current_app:
                current_app.logger.error(
                    f"GitHub error listing contents of '{norm_folder}': {extract_github_error_message(e)}"
                )
            return []

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Retrieve metadata for a single file.
        Raises PermissionError if path outside storage.
        Raises IsADirectoryError if path is a directory.
        Raises GithubException (e.g. 404) if not found.
        """
        norm_path = self.normalize_storage_path(file_path)
        c = self.repo.get_contents(norm_path, ref=self.branch)
        if isinstance(c, list) or getattr(c, "type", "file") == "dir":
            raise IsADirectoryError("Path is a directory")

        display_name = c.name
        return {
            "name": display_name,
            "path": c.path,
            "size": c.size,
            "size_formatted": self.format_bytes(c.size),
            "download_url": self.get_direct_download_url(c.path),
            "stream_url": f"/download/{self.get_display_path(c.path)}",
            "mime_type": self.get_mime_type(display_name),
            "sha": c.sha,
        }

    def upload_file(self, filename: str, data: bytes, folder: str = "") -> Dict[str, Any]:
        """
        Uploads or updates a file in storage.
        Protects against folder collisions (AttributeError prevention).
        Invalidates directory cache on success.
        """
        norm_folder = self.normalize_storage_path(folder)
        safe_filename = sanitize_filename(filename)
        path = f"{norm_folder}/{safe_filename}"
        timestamp = datetime.now(UTC).isoformat()
        commit_message = f"Upload {safe_filename} @ {timestamp}"

        is_updated = False
        try:
            existing = self.repo.get_contents(path, ref=self.branch)
            if isinstance(existing, list) or getattr(existing, "type", "file") == "dir":
                raise IsADirectoryError(f"A folder with name '{safe_filename}' already exists.")

            self.repo.update_file(path, commit_message, data, existing.sha, branch=self.branch)
            is_updated = True
        except GithubException as e:
            if e.status == 404:
                self.repo.create_file(path, commit_message, data, branch=self.branch)
                is_updated = False
            else:
                raise

        # Invalidate cache for the folder
        self.cache.invalidate(norm_folder)

        return {
            "filename": safe_filename,
            "path": path,
            "updated": is_updated,
        }

    def create_folder(self, folder: str, folder_name: str) -> Dict[str, Any]:
        """
        Creates a new folder by committing a .gitkeep marker file.
        Handles duplicate folder 422 errors gracefully.
        Invalidates parent and child cache entries.
        """
        norm_folder = self.normalize_storage_path(folder)
        safe_folder_name = sanitize_filename(folder_name)
        new_folder_path = f"{norm_folder}/{safe_folder_name}/.gitkeep"
        commit_message = f"Create folder '{safe_folder_name}' @ {datetime.now(UTC).isoformat()}"

        try:
            self.repo.create_file(new_folder_path, commit_message, b"", branch=self.branch)
        except GithubException as e:
            err_text = str(e.data).lower() if e.data else str(e).lower()
            if (e.status in (422, 409)) and any(p in err_text for p in ("sha", "already exists", "file exists")):
                raise FileExistsError("Folder already exists.")
            raise

        # Invalidate cache for parent folder and newly created folder
        self.cache.invalidate_folder_and_relations(f"{norm_folder}/{safe_folder_name}")

        return {
            "folder": f"{norm_folder}/{safe_folder_name}",
            "name": safe_folder_name,
        }

    def delete_file(self, file_path: str) -> bool:
        """
        Deletes a single file from storage.
        Invalidates directory cache on success.
        """
        norm_path = self.normalize_storage_path(file_path)
        if norm_path == "storage":
            raise PermissionError("Cannot delete root storage directory")

        c = self.repo.get_contents(norm_path, ref=self.branch)
        if isinstance(c, list) or getattr(c, "type", "file") == "dir":
            raise IsADirectoryError("Use folder delete endpoint for directories")

        commit_message = f"Delete {norm_path} @ {datetime.now(UTC).isoformat()}"
        self.repo.delete_file(norm_path, commit_message, c.sha, branch=self.branch)

        # Invalidate parent directory cache
        parent_folder = norm_path.rsplit("/", 1)[0]
        self.cache.invalidate(parent_folder)
        return True

    def delete_folder(self, folder_path: str) -> bool:
        """
        Recursively deletes a folder and all its contents.
        Guarantees root storage folder cannot be deleted.
        Invalidates folder, parent, and descendants in cache.
        """
        norm_path = self.normalize_storage_path(folder_path)
        if norm_path == "storage":
            raise PermissionError("Cannot delete root storage directory")

        def _recursive_delete(path: str) -> None:
            contents = self.repo.get_contents(path, ref=self.branch)
            if not isinstance(contents, list):
                contents = [contents]

            for item in contents:
                if item.type == "dir":
                    _recursive_delete(item.path)
                else:
                    msg = f"Delete {item.path} @ {datetime.now(UTC).isoformat()}"
                    self.repo.delete_file(item.path, msg, item.sha, branch=self.branch)

        _recursive_delete(norm_path)
        self.cache.invalidate_folder_and_relations(norm_path)
        return True

    def download_from_url(self, url: str, max_size: int) -> Tuple[str, bytes]:
        """Safely download remote file using SSRF validation and bounded streaming."""
        return safe_download_from_url(url=url, max_size=max_size)

    def stream_file(self, file_path: str) -> Tuple[str, str, Optional[int], Generator[bytes, None, None]]:
        """
        Stream file content in 64KB chunks.
        Supports both public and private repositories via authenticated requests.

        Returns:
          (filename, mime_type, content_length, chunk_generator)
        """
        norm_path = self.normalize_storage_path(file_path)
        c = self.repo.get_contents(norm_path, ref=self.branch)
        if isinstance(c, list) or getattr(c, "type", "file") == "dir":
            raise IsADirectoryError("Cannot download directory directly")

        filename = c.name
        mime_type = self.get_mime_type(filename)
        content_length = c.size

        token = self.token
        repo_name = self.repo_name
        branch = self.branch

        def generate_chunks() -> Generator[bytes, None, None]:
            # Method 1: Try raw.githubusercontent.com with Authorization header
            raw_url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/{norm_path}"
            headers = {"Authorization": f"token {token}"} if token else {}
            try:
                with requests.get(raw_url, headers=headers, stream=True, timeout=30) as r:
                    if r.status_code == 200:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                yield chunk
                        return
            except requests.RequestException:
                pass

            # Method 2: Fallback to GitHub REST API raw media stream
            api_url = f"https://api.github.com/repos/{repo_name}/contents/{norm_path}?ref={branch}"
            api_headers = {
                "Accept": "application/vnd.github.raw",
                "User-Agent": "Storista-App",
            }
            if token:
                api_headers["Authorization"] = f"Bearer {token}"

            with requests.get(api_url, headers=api_headers, stream=True, timeout=30) as r_api:
                if r_api.status_code != 200:
                    raise GithubException(r_api.status_code, r_api.text, dict(r_api.headers))
                for chunk in r_api.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk

        return filename, mime_type, content_length, generate_chunks()


def get_github_service() -> GitHubService:
    """Retrieve GitHubService from Flask current_app context."""
    return current_app.extensions["github_service"]
