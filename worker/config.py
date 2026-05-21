"""Worker configuration — all settings from environment variables."""

import os

# Database (Turso in prod, local SQLite in dev)
TURSO_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/automations.db")

# Groq API keys — comma-separated for multi-key rotation
_groq_keys_raw = os.getenv("GROQ_API_KEYS", os.getenv("GROQ_API_KEY", ""))
GROQ_API_KEYS: list[str] = [k.strip() for k in _groq_keys_raw.split(",") if k.strip()]

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_REQUEST_INTERVAL = float(os.getenv("GROQ_REQUEST_INTERVAL", "4.5"))

# Resend
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "noreply@example.com")

# Browser / scraper
CHROME_STEALTH = os.getenv("CHROME_STEALTH", "true").lower() == "true"
# CHROME_HEADLESS=true uses Chrome's "new" headless mode (close to headed, harder
# to detect). On a Linux VPS without Xvfb this is required. On a VPS with Xvfb,
# leave it false so Chrome runs headed against the virtual display.
CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "false").lower() == "true"
# CHROME_BINARY can override the executable (e.g. /usr/bin/google-chrome-stable)
CHROME_BINARY = os.getenv("CHROME_BINARY", "")
NAV_TIMEOUT = int(os.getenv("NAV_TIMEOUT_MS", "30000"))
SETTLE_SECONDS = float(os.getenv("SETTLE_SECONDS", "3.0"))

# Worker poll interval
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
