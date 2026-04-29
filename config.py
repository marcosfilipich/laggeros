import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or f"sqlite:///{BASE_DIR / 'laggeros.sqlite'}"
    )

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or str(BASE_DIR / "uploads")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB total request size

    # Cookie security. *_SECURE flags default to False so local HTTP dev no rompe;
    # en prod estamos detras de nginx + Let's Encrypt, asi que hay que setear
    # SESSION_COOKIE_SECURE=true y REMEMBER_COOKIE_SECURE=true en /home/marcos/laggeros/.env
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool("REMEMBER_COOKIE_SECURE")
    REMEMBER_COOKIE_HTTPONLY = True
