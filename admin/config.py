"""Admin Panel Configuration"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import secrets

# JWT
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# Database — используйте ADMIN_DATABASE_URL для отдельной БД админ-панели
# По умолчанию SQLite (не требует PostgreSQL/greenlet)
DATABASE_URL = os.getenv("ADMIN_DATABASE_URL") or os.getenv("DATABASE_URL", "sqlite:///admin_panel.db")

# Redis (опционально, для кеширования)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Admin
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Paths
STATIC_DIR = Path(__file__).resolve().parent / "static"

# CORS
CORS_ORIGINS = [
    os.getenv("CORS_ORIGIN", "*"),
]

# WebApp base URL (for admin panel link)
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "http://localhost:8080")
ADMIN_PANEL_URL = os.getenv("ADMIN_PANEL_URL", "http://localhost:8000")
