"""Auto-respuestas / FAQ por grupo (Premium)."""
from __future__ import annotations

import re

from sqlalchemy import select

from db.models import FaqEntry
from services import session_scope


async def set_entry(group_id: int, keyword: str, answer: str) -> None:
    keyword = keyword.lower().strip()
    async with session_scope() as s:
        res = await s.execute(select(FaqEntry).where(
            FaqEntry.group_id == group_id, FaqEntry.keyword == keyword))
        row = res.scalar_one_or_none()
        if row:
            row.answer = answer
        else:
            s.add(FaqEntry(group_id=group_id, keyword=keyword, answer=answer))


async def delete(group_id: int, keyword: str) -> bool:
    async with session_scope() as s:
        res = await s.execute(select(FaqEntry).where(
            FaqEntry.group_id == group_id, FaqEntry.keyword == keyword.lower().strip()))
        row = res.scalar_one_or_none()
        if not row:
            return False
        await s.delete(row)
        return True


async def list_for(group_id: int) -> list[dict]:
    async with session_scope() as s:
        res = await s.execute(select(FaqEntry).where(FaqEntry.group_id == group_id))
        return [{"keyword": r.keyword, "answer": r.answer} for r in res.scalars()]


async def match(group_id: int, text: str) -> str | None:
    """Devuelve la respuesta si alguna palabra clave aparece en el texto."""
    if not text:
        return None
    words = set(re.findall(r"[\wáéíóúñ]+", text.lower()))
    if not words:
        return None
    async with session_scope() as s:
        res = await s.execute(select(FaqEntry).where(FaqEntry.group_id == group_id))
        for r in res.scalars():
            if r.keyword in words:
                return r.answer
    return None
