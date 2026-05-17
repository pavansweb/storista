# Storista ☁️

A sleek, lightweight cloud storage solution powered by GitHub.

## Features

-   **Backend:** Powered by Flask and PyGithub.
-   **Storage:** Uses a GitHub repository as a persistent backend.
-   **UI:** Modern, responsive design with Bootstrap 5.
-   **Functionality:**
    *   Upload files (local or via URL).
    *   Create and manage folders.
    *   Direct download from GitHub.
    *   Recursive folder deletion.
    *   Search and sort files.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/pavansweb/storista.git
    cd storista
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure environment variables:**
    Copy `.env.example` to `.env` and fill in your details:
    *   `GIT_TOKEN`: Your GitHub Personal Access Token.
    *   `GIT_REPO`: The repository to use for storage (e.g., `username/storage-repo`).
    *   `GITHUB_BRANCH`: The branch to use (default: `main`).
    *   `FLASK_SECRET`: A random string for session security.

4.  **Run the application:**
    ```bash
    python app.py
    ```
    The app will be available at `http://localhost:5001`.

## Deployment

Storista is designed to be easily deployable to platforms like Vercel or Heroku. Ensure you set the environment variables in your deployment platform's settings.

## License

MIT
