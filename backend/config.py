"""All settings, read from environment variables (see .env.example).

Nothing else in the backend reads os.environ directly, so this file is the one
place to look when deploying.

  LOSTPOINT_DB            SQLite file (default backend/lostpoint.db)
  LOSTPOINT_CORS_ORIGINS  comma-separated origins allowed to call the API from a
                          browser on another host (default: none; the Vite dev
                          proxy and the single-container deploy are same-origin)
  LOSTPOINT_STATIC_DIR    serve the built frontend from here (the Docker image sets it)
  LOSTPOINT_STAFF_CODE    code needed to register a lecturer or tutor account;
                          unset means staff can only be created with `python accounts.py`
  LOSTPOINT_SESSION_DAYS  how long a login lasts (default 14)
  LOSTPOINT_SEARCH        "fts" (default, no downloads) or "chroma" (semantic, needs chromadb)
  LOSTPOINT_CHROMA_DIR    where Chroma keeps its index (default backend/chroma)
  LOSTPOINT_LOG_LEVEL     INFO by default
  ELEVENLABS_API_KEY      server-only key for issuing realtime Scribe tokens
"""

import os
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))


class Settings:
    def __init__(self):
        env = os.environ.get
        self.db_path = env("LOSTPOINT_DB") or os.path.join(HERE, "lostpoint.db")
        self.cors_origins = [o.strip() for o in (env("LOSTPOINT_CORS_ORIGINS") or "").split(",") if o.strip()]
        self.static_dir = env("LOSTPOINT_STATIC_DIR") or None
        self.staff_code = env("LOSTPOINT_STAFF_CODE") or None
        self.session_days = int(env("LOSTPOINT_SESSION_DAYS") or 14)
        self.search = (env("LOSTPOINT_SEARCH") or "fts").lower()
        self.chroma_dir = env("LOSTPOINT_CHROMA_DIR") or os.path.join(HERE, "chroma")
        self.log_level = (env("LOSTPOINT_LOG_LEVEL") or "INFO").upper()
        self.elevenlabs_api_key = env("ELEVENLABS_API_KEY") or ""


@lru_cache
def _cached() -> Settings:
    return Settings()


def settings() -> Settings:
    # Tests change the environment between runs; re-read when they do.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return Settings()
    return _cached()
