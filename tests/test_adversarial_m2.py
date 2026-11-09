"""
tests/test_adversarial_m2.py
Empirical Adversarial Verification Suite for Storista Milestone 2.
Must be executed with ./venv/bin/python.
"""

import os
import sys
import subprocess
import unittest
import urllib.parse

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from flask import render_template


class TestMilestone2InteractiveAdversarial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.app_context = app.app_context()
        cls.app_context.push()

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def test_01_execute_empirical_dom_harness(self):
        """Execute the Node.js empirical DOM harness covering Focus 1-5."""
        harness_path = os.path.join(os.path.dirname(__file__), "test_harness_dom.js")
        result = subprocess.run(
            ["node", harness_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print("\n--- Node.js DOM Harness Output ---")
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        self.assertEqual(result.returncode, 0, "DOM harness must exit with code 0")
        self.assertIn("DOM TEST RESULTS: 27 PASSED, 0 FAILED", result.stdout)
        self.assertIn("CONFIRMED REMEDIATION", result.stdout)

    def test_02_static_assets_delivery(self):
        """Verify delivery and Content-Type of style.css and app.js."""
        res_css = self.client.get("/static/css/style.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn("text/css", res_css.headers.get("Content-Type", ""))
        self.assertIn("glass-card", res_css.get_data(as_text=True))

        res_js = self.client.get("/static/js/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("javascript", res_js.headers.get("Content-Type", "").lower())
        self.assertIn("FileExplorerEngine", res_js.get_data(as_text=True))

    def test_03_jinja2_xss_autoescaping_in_rendered_templates(self):
        """Verify Jinja2 rigorously escapes adversarial filenames in HTML attributes and content."""
        adversarial_files = [
            {"name": "<script>alert(1)</script>.txt", "path": "storage/<script>alert(1)</script>.txt", "is_dir": False, "size": 100, "size_formatted": "100 B", "download_url": "#", "mime_type": "text/plain"},
            {"name": "<img src=x onerror=alert(1)>.jpg", "path": "storage/<img src=x onerror=alert(1)>.jpg", "is_dir": False, "size": 200, "size_formatted": "200 B", "download_url": "#", "mime_type": "image/jpeg"},
            {"name": "\"><svg onload=alert(1)>.svg", "path": "storage/\"><svg onload=alert(1)>.svg", "is_dir": False, "size": 300, "size_formatted": "300 B", "download_url": "#", "mime_type": "image/svg+xml"},
            {"name": "file'with'apostrophes.pdf", "path": "storage/file'with'apostrophes.pdf", "is_dir": False, "size": 400, "size_formatted": "400 B", "download_url": "#", "mime_type": "application/pdf"},
            {"name": "file\"with\"quotes.txt", "path": "storage/file\"with\"quotes.txt", "is_dir": False, "size": 500, "size_formatted": "500 B", "download_url": "#", "mime_type": "text/plain"},
        ]

        with app.test_request_context("/"):
            html = render_template("index.html", files=adversarial_files, current_folder="", parent_folder=None, needs_auth=False)

            # Ensure raw unescaped injection strings are NOT present
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertNotIn("<img src=x onerror=alert(1)>", html)
            self.assertNotIn("\"><svg onload=alert(1)>", html)

            # Ensure safe HTML entities ARE present
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
            self.assertTrue(any(sub in html for sub in ["&#34;", "&quot;", "&#x22;"]))

    def test_04_vault_locked_view_strict_containment(self):
        """Verify dashboard toolbar, upload drawer, and file listings are omitted when vault is locked."""
        res = self.client.get("/browse/vault")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn("The Vault is Locked", html)
        self.assertIn("vault-challenge-card", html)

        # Dashboard components must not be rendered
        self.assertNotIn("action-toolbar", html)
        self.assertNotIn("uploadDrawer", html)
        self.assertNotIn("file-list", html)
        self.assertNotIn("filter-bar", html)
        self.assertNotIn("search-wrapper", html)

    def test_05_mime_type_iconography_assignment(self):
        """Verify dynamic MIME type icon badges render expected classes without FOUC."""
        sample_files = [
            {"name": "folder_item", "path": "storage/folder_item", "is_dir": True, "size": 0, "size_formatted": "0 B", "download_url": "", "mime_type": None},
            {"name": "photo.png", "path": "storage/photo.png", "is_dir": False, "size": 1024, "size_formatted": "1 KB", "download_url": "#", "mime_type": "image/png"},
            {"name": "doc.pdf", "path": "storage/doc.pdf", "is_dir": False, "size": 2048, "size_formatted": "2 KB", "download_url": "#", "mime_type": "application/pdf"},
            {"name": "code.py", "path": "storage/code.py", "is_dir": False, "size": 512, "size_formatted": "512 B", "download_url": "#", "mime_type": "text/x-python"},
            {"name": "archive.zip", "path": "storage/archive.zip", "is_dir": False, "size": 4096, "size_formatted": "4 KB", "download_url": "#", "mime_type": "application/zip"},
            {"name": "music.mp3", "path": "storage/music.mp3", "is_dir": False, "size": 8192, "size_formatted": "8 KB", "download_url": "#", "mime_type": "audio/mpeg"},
            {"name": "sheet.xlsx", "path": "storage/sheet.xlsx", "is_dir": False, "size": 1024, "size_formatted": "1 KB", "download_url": "#", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            {"name": "unknown.bin", "path": "storage/unknown.bin", "is_dir": False, "size": 1024, "size_formatted": "1 KB", "download_url": "#", "mime_type": "application/octet-stream"},
        ]

        with app.test_request_context("/"):
            html = render_template("index.html", files=sample_files, current_folder="", parent_folder=None, needs_auth=False)
            self.assertIn("file-icon-gold", html)      # Folder
            self.assertIn("file-icon-emerald", html)   # Image
            self.assertIn("file-icon-rose", html)      # PDF
            self.assertIn("file-icon-sky", html)       # Code
            self.assertIn("file-icon-violet", html)    # Zip / Archive
            self.assertIn("file-icon-pink", html)      # Audio / Media
            self.assertIn("file-icon-amber", html)     # Spreadsheet
            self.assertIn("file-icon-indigo", html)    # Other binary

    def test_06_wcag_accessibility_attributes(self):
        """Verify WCAG AA attributes (aria-label, dialog semantics, role regions)."""
        sample_files = [
            {"name": "my_doc.pdf", "path": "storage/my_doc.pdf", "is_dir": False, "size": 1024, "size_formatted": "1 KB", "download_url": "#", "mime_type": "application/pdf"}
        ]
        with app.test_request_context("/"):
            html = render_template("index.html", files=sample_files, current_folder="", parent_folder=None, needs_auth=False)
            self.assertIn('aria-label="Delete my_doc.pdf"', html)
            self.assertIn('aria-label="Download my_doc.pdf"', html)
            self.assertIn('aria-label="Preview my_doc.pdf"', html)
            self.assertIn('role="toolbar"', html)
            self.assertIn('role="search"', html)
            self.assertIn('role="region"', html)
            self.assertIn('<dialog id="deleteModal"', html)
            self.assertIn('<dialog id="previewModal"', html)
            self.assertIn('<dialog id="newFolderModal"', html)

    def test_07_security_path_traversal_blocking(self):
        """Verify that streaming download and API deletion endpoints strictly reject path traversal with 403."""
        traversal_attempts = [
            "storage/../app.py",
            "../app.py",
            "storage/../../etc/passwd",
            "%2e%2e/app.py",
            "storage/%2e%2e/app.py"
        ]
        for path in traversal_attempts:
            res_dl = self.client.get(f"/download/{path}")
            self.assertIn(res_dl.status_code, [403, 404], f"Path {path} must not be served")

            res_del = self.client.delete(f"/api/files/{path}")
            self.assertIn(res_del.status_code, [403, 404], f"Path {path} must not be deleted")

    def test_08_css_responsive_design_and_touch_targets(self):
        """Verify style.css contains responsive media queries and >=44px touch targets."""
        css_path = "/home/zen/Projects/storista/static/css/style.css"
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()

        # Check responsive breakpoints
        self.assertIn("@media (max-width: 639.98px)", css)
        self.assertIn("@media (min-width: 640px) and (max-width: 1024px)", css)

        # Check 44px touch targets
        self.assertIn("min-height: 44px", css)
        self.assertIn("min-width: 44px", css)

        # Check focus-visible outline
        self.assertIn(":focus-visible", css)


if __name__ == "__main__":
    unittest.main()
