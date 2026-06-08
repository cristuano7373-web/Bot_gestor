"""Configuración central cargada desde variables de entorno (.env)."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _ids(raw: str) -> set[int]:
    out = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS: set[int] = _ids(os.getenv("ADMIN_IDS", ""))


def _normalize_db_url(url: str) -> str:
    """Adapta la URL de la BD al driver async.

    Railway/Heroku entregan 'postgres://...' o 'postgresql://...'; SQLAlchemy
    async necesita 'postgresql+asyncpg://...'. Esta conversión evita el error
    de conexión más típico al desplegar.
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    # asyncpg no entiende el parámetro sslmode en la URL; lo quitamos si viene.
    if "+asyncpg://" in url and "sslmode=" in url:
        import re
        url = re.sub(r"[?&]sslmode=[^&]*", "", url)
    return url


DATABASE_URL: str = _normalize_db_url(
    os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot_gestor.db"))

FERNET_KEY: str = os.getenv("FERNET_KEY", "").strip()

PREMIUM_STARS_PRICE: int = int(os.getenv("PREMIUM_STARS_PRICE", "150") or "150")
PREMIUM_DAYS: int = int(os.getenv("PREMIUM_DAYS", "30") or "30")

TIMEZONE: str = os.getenv("TIMEZONE", "UTC").strip() or "UTC"
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()


def validate() -> None:
    """Valida configuración esencial y avisa de fallos comunes."""
    if not BOT_TOKEN or BOT_TOKEN.startswith("123456789:"):
        raise SystemExit(
            "ERROR: configura BOT_TOKEN en .env (token de @BotFather)."
        )
    if not ADMIN_IDS:
        raise SystemExit(
            "ERROR: configura ADMIN_IDS en .env (tu ID de Telegram). "
            "Obtén tu ID escribiendo a @userinfobot."
        )


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
