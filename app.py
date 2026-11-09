"""
app.py
~~~~~~
Storista WSGI application entrypoint.

Backward Compatibility:
- Vercel Serverless: vercel.json routes to `app.py` looking for `app`.
- Gunicorn: Invoked via `gunicorn app:app`.
- Development: Invoked via `python app.py`.
"""

from storista import create_app

# Instantiate default application for WSGI servers
app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
