"""Gestión del estado Premium por grupo (suscripciones)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models import Subscription
from services import session_scope


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Garantiza que la fecha tenga zona (SQLite puede devolverla naive)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def get_subscription(group_id: int) -> dict | None:
    async with session_scope() as s:
        sub = await _get(s, group_id)
        if sub is None:
            return None
        return _to_dict(sub)


async def is_premium(group_id: int) -> bool:
    async with session_scope() as s:
        sub = await _get(s, group_id)
        if sub is None or sub.plan != "premium":
            return False
        exp = _aware(sub.expires_at)
        if exp is None:
            return True  # premium sin caducidad (raro)
        return exp > _now()


async def activate_premium(group_id: int, *, days: int, source: str,
                           activated_by: int, auto_renew: bool = False) -> dict:
    """Activa o extiende Premium. Si ya estaba activo, suma los días."""
    async with session_scope() as s:
        sub = await _get(s, group_id)
        base = _now()
        if sub is None:
            sub = Subscription(group_id=group_id)
            s.add(sub)
        else:
            exp = _aware(sub.expires_at)
            if sub.plan == "premium" and exp and exp > base:
                base = exp  # extender desde la fecha actual de expiración
        sub.plan = "premium"
        sub.source = source
        sub.expires_at = base + timedelta(days=days)
        sub.auto_renew = auto_renew
        sub.activated_by = activated_by
        await s.flush()
        return _to_dict(sub)


async def expire_due() -> int:
    """Marca como 'free' las suscripciones vencidas. Devuelve cuántas expiraron."""
    async with session_scope() as s:
        result = await s.execute(
            select(Subscription).where(Subscription.plan == "premium")
        )
        count = 0
        now = _now()
        for sub in result.scalars():
            exp = _aware(sub.expires_at)
            if exp and exp <= now:
                sub.plan = "free"
                sub.source = None
                sub.auto_renew = False
                count += 1
        return count


async def _get(session, group_id: int) -> Subscription | None:
    res = await session.execute(
        select(Subscription).where(Subscription.group_id == group_id)
    )
    return res.scalar_one_or_none()


def _to_dict(sub: Subscription) -> dict:
    exp = _aware(sub.expires_at)
    days_left = None
    if exp:
        days_left = max(0, (exp - _now()).days)
    return {
        "group_id": sub.group_id,
        "plan": sub.plan,
        "source": sub.source,
        "expires_at": exp.isoformat() if exp else None,
        "days_left": days_left,
        "auto_renew": sub.auto_renew,
        "active": sub.plan == "premium" and (exp is None or exp > _now()),
    }
