"""Alta/actualización de usuarios y grupos, y registro de auditoría."""
from __future__ import annotations

from sqlalchemy import select

from db.models import AuditLog, Group, User
from services import session_scope


async def ensure_user(user_id: int, username: str | None, first_name: str | None) -> None:
    async with session_scope() as s:
        u = await s.get(User, user_id)
        if u is None:
            s.add(User(id=user_id, username=username, first_name=first_name))
        else:
            u.username = username
            u.first_name = first_name


async def ensure_group(chat_id: int, title: str | None, added_by: int | None = None) -> None:
    async with session_scope() as s:
        g = await s.get(Group, chat_id)
        if g is None:
            s.add(Group(id=chat_id, title=title, added_by=added_by))
        else:
            if title:
                g.title = title
            g.is_active = True


async def audit(actor_id: int | None, action: str, detail: str | None = None) -> None:
    async with session_scope() as s:
        s.add(AuditLog(actor_id=actor_id, action=action, detail=detail))


async def get_lang(user_id: int) -> str:
    """Idioma del usuario ('es'/'en'). Por defecto 'es'."""
    async with session_scope() as s:
        u = await s.get(User, user_id)
        return (u.lang if u and u.lang else "es")


async def set_lang(user_id: int, lang: str) -> None:
    async with session_scope() as s:
        u = await s.get(User, user_id)
        if u is None:
            s.add(User(id=user_id, lang=lang))
        else:
            u.lang = lang
