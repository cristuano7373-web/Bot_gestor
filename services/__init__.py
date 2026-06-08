"""Lógica de negocio (sin dependencias de Telegram)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from db.base import get_sessionmaker


@asynccontextmanager
async def session_scope():
    """Abre una sesión y hace commit/rollback automático."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
