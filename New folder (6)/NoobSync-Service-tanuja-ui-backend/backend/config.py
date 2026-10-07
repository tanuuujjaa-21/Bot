"""
config.py
Central settings for the backend. Everything is env-overridable so the same
code runs on a laptop and on a server without edits.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ── Storage ────────────────────────────────────────────────────────────────
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "app.db"
DOCS_DIR = DATA_DIR / "docs"          # extracted text of each user's uploads

# ── Uploads ────────────────────────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "15"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_FILES_PER_REQUEST = int(os.environ.get("MAX_FILES_PER_REQUEST", "10"))
MAX_DOCS_PER_USER = int(os.environ.get("MAX_DOCS_PER_USER", "20"))
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".csv")

# ── Auth ───────────────────────────────────────────────────────────────────
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))
REGISTER_LIMIT = int(os.environ.get("REGISTER_LIMIT", "10"))            # per IP
REGISTER_WINDOW_SECONDS = int(os.environ.get("REGISTER_WINDOW_SECONDS", "600"))

# ── HTTP ───────────────────────────────────────────────────────────────────
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

DATA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
