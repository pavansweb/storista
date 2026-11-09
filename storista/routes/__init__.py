"""
storista.routes
~~~~~~~~~~~~~~~
Routes package for Storista.
"""

from storista.routes.web import web_bp
from storista.routes.api import api_bp

__all__ = ["web_bp", "api_bp"]
