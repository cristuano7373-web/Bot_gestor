"""Consulta y gestión del historial de pagos (Telegram Stars)."""
from __future__ import annotations

from sqlalchemy import select

from db.models import Payment
from services import session_scope


async def get_last_paid() -> dict | None:
    """Devuelve el último pago en estado 'paid' (para reembolso rápido)."""
    async with session_scope() as s:
        res = await s.execute(
            select(Payment).where(Payment.status == "paid")
            .order_by(Payment.id.desc()).limit(1)
        )
        p = res.scalar_one_or_none()
        return _to_dict(p) if p else None


async def get_by_charge(charge_id: str) -> dict | None:
    async with session_scope() as s:
        res = await s.execute(
            select(Payment).where(Payment.telegram_charge_id == charge_id))
        p = res.scalar_one_or_none()
        return _to_dict(p) if p else None


async def list_paid(limit: int = 10) -> list[dict]:
    async with session_scope() as s:
        res = await s.execute(
            select(Payment).order_by(Payment.id.desc()).limit(limit))
        return [_to_dict(p) for p in res.scalars()]


async def mark_refunded(charge_id: str) -> None:
    async with session_scope() as s:
        res = await s.execute(
            select(Payment).where(Payment.telegram_charge_id == charge_id))
        p = res.scalar_one_or_none()
        if p:
            p.status = "refunded"


def _to_dict(p: Payment) -> dict:
    return {
        "id": p.id, "user_id": p.user_id, "group_id": p.group_id,
        "amount": p.amount, "charge_id": p.telegram_charge_id,
        "status": p.status,
    }
