"""Estadísticas: registro de actividad, rankings y reportes."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from db.models import MessageStat, Payment, Subscription
from services import session_scope


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def record_message(group_id: int, user_id: int, *, new_member: bool = False) -> None:
    async with session_scope() as s:
        day = _today()
        res = await s.execute(
            select(MessageStat).where(
                MessageStat.group_id == group_id,
                MessageStat.user_id == user_id,
                MessageStat.day == day,
            )
        )
        row = res.scalar_one_or_none()
        if row is None:
            s.add(MessageStat(group_id=group_id, user_id=user_id, day=day,
                              messages=0 if new_member else 1,
                              is_new_member=new_member))
        else:
            if not new_member:
                row.messages += 1
            if new_member:
                row.is_new_member = True


async def group_summary(group_id: int, days: int = 7) -> dict:
    """Resumen de actividad de los últimos `days` días."""
    since = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    async with session_scope() as s:
        # Totales
        total_msgs = await s.scalar(
            select(func.coalesce(func.sum(MessageStat.messages), 0)).where(
                MessageStat.group_id == group_id, MessageStat.day >= since)
        )
        active_users = await s.scalar(
            select(func.count(func.distinct(MessageStat.user_id))).where(
                MessageStat.group_id == group_id, MessageStat.day >= since,
                MessageStat.messages > 0)
        )
        new_members = await s.scalar(
            select(func.count()).where(
                MessageStat.group_id == group_id, MessageStat.day >= since,
                MessageStat.is_new_member == True)  # noqa: E712
        )
        # Serie diaria (para gráficos / sparkline)
        res = await s.execute(
            select(MessageStat.day, func.sum(MessageStat.messages))
            .where(MessageStat.group_id == group_id, MessageStat.day >= since)
            .group_by(MessageStat.day).order_by(MessageStat.day)
        )
        daily = {d: int(m or 0) for d, m in res.all()}
        return {
            "days": days,
            "total_messages": int(total_msgs or 0),
            "active_users": int(active_users or 0),
            "new_members": int(new_members or 0),
            "daily": daily,
        }


async def ranking(group_id: int, days: int = 7, limit: int = 10) -> list[dict]:
    since = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    async with session_scope() as s:
        res = await s.execute(
            select(MessageStat.user_id, func.sum(MessageStat.messages).label("m"))
            .where(MessageStat.group_id == group_id, MessageStat.day >= since)
            .group_by(MessageStat.user_id).order_by(func.sum(MessageStat.messages).desc())
            .limit(limit)
        )
        return [{"user_id": uid, "messages": int(m or 0)} for uid, m in res.all()]


async def global_stats() -> dict:
    """Estadísticas globales del producto (para el admin)."""
    async with session_scope() as s:
        groups = await s.scalar(select(func.count(func.distinct(MessageStat.group_id))))
        premium = await s.scalar(
            select(func.count()).where(Subscription.plan == "premium"))
        revenue = await s.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid"))
        return {
            "groups_with_activity": int(groups or 0),
            "premium_groups": int(premium or 0),
            "stars_revenue": int(revenue or 0),
        }


def daily_series(summary: dict, days: int) -> list[tuple[str, int]]:
    """Rellena los días faltantes con 0 para gráficos coherentes."""
    end = datetime.now(timezone.utc).date()
    out = []
    for i in range(days - 1, -1, -1):
        d = (end - timedelta(days=i)).isoformat()
        out.append((d, summary["daily"].get(d, 0)))
    return out
