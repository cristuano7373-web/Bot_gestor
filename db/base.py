"""Motor, sesiones y base declarativa.

Una sola capa de código sirve para PostgreSQL (producción, asyncpg) y SQLite
(desarrollo/tests, aiosqlite). Solo cambia DATABASE_URL.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

import config


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None):
    """Crea el engine y el sessionmaker (idempotente)."""
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(
            url or config.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        init_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def create_all() -> None:
    """Crea las tablas si no existen (para arranque y tests)."""
    from db import models  # noqa: F401  (registra los modelos)
    engine = init_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
