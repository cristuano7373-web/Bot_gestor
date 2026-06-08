"""Federación: lista negra global por dueño del bot (Premium).

Un administrador puede banear a un usuario en TODOS sus grupos a la vez.
La aplicación efectiva del ban en cada grupo la hace el handler (necesita la API
de Telegram); aquí solo se guarda la lista y se consultan los grupos del dueño.
"""
from __future__ import annotations

from sqlalchemy import select

from db.models import FedBan, Group
from services import session_scope


async def add_ban(owner_id: int, user_id: int, reason: str | None) -> None:
    async with session_scope() as s:
        res = await s.execute(select(FedBan).where(
            FedBan.owner_id == owner_id, FedBan.user_id == user_id))
        if res.scalar_one_or_none() is None:
            s.add(FedBan(owner_id=owner_id, user_id=user_id, reason=reason))


async def remove_ban(owner_id: int, user_id: int) -> bool:
    async with session_scope() as s:
        res = await s.execute(select(FedBan).where(
            FedBan.owner_id == owner_id, FedBan.user_id == user_id))
        row = res.scalar_one_or_none()
        if not row:
            return False
        await s.delete(row)
        return True


async def is_banned(owner_id: int, user_id: int) -> bool:
    async with session_scope() as s:
        res = await s.execute(select(FedBan.id).where(
            FedBan.owner_id == owner_id, FedBan.user_id == user_id))
        return res.scalar_one_or_none() is not None


async def owner_groups(owner_id: int) -> list[int]:
    """Grupos registrados que añadió este dueño (donde aplicar el ban)."""
    async with session_scope() as s:
        res = await s.execute(select(Group.id).where(
            Group.added_by == owner_id, Group.is_active == True))  # noqa: E712
        return [r for r in res.scalars()]


async def list_bans(owner_id: int) -> list[dict]:
    async with session_scope() as s:
        res = await s.execute(select(FedBan).where(FedBan.owner_id == owner_id))
        return [{"user_id": r.user_id, "reason": r.reason} for r in res.scalars()]
