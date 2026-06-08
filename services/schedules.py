"""Mensajes programados por grupo (Premium)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from db.models import ScheduledMessage
from services import session_scope


async def add(group_id: int, text: str, *, run_at: datetime | None,
              interval_s: int | None, created_by: int) -> int:
    async with session_scope() as s:
        row = ScheduledMessage(
            group_id=group_id, text=text,
            run_at=run_at, interval_s=interval_s, created_by=created_by)
        s.add(row)
        await s.flush()
        return row.id


async def get(sched_id: int) -> dict | None:
    async with session_scope() as s:
        row = await s.get(ScheduledMessage, sched_id)
        return _to_dict(row) if row else None


async def list_for(group_id: int) -> list[dict]:
    async with session_scope() as s:
        res = await s.execute(
            select(ScheduledMessage).where(
                ScheduledMessage.group_id == group_id,
                ScheduledMessage.active == True)  # noqa: E712
            .order_by(ScheduledMessage.id))
        return [_to_dict(r) for r in res.scalars()]


async def all_active() -> list[dict]:
    async with session_scope() as s:
        res = await s.execute(
            select(ScheduledMessage).where(ScheduledMessage.active == True))  # noqa: E712
        return [_to_dict(r) for r in res.scalars()]


async def deactivate(sched_id: int, group_id: int | None = None) -> bool:
    async with session_scope() as s:
        row = await s.get(ScheduledMessage, sched_id)
        if not row or (group_id is not None and row.group_id != group_id):
            return False
        row.active = False
        return True


def _to_dict(r: ScheduledMessage) -> dict:
    run = r.run_at
    if run is not None and run.tzinfo is None:
        run = run.replace(tzinfo=timezone.utc)
    return {
        "id": r.id, "group_id": r.group_id, "text": r.text,
        "run_at": run.isoformat() if run else None,
        "interval_s": r.interval_s, "active": r.active,
    }
