"""Sistema de licencias (Método A): generación, canje y revocación.

Protección anti-doble-canje:
  - Código único (constraint en BD).
  - El canje se hace en UNA transacción: se relee la licencia y se marca como
    canjeada solo si seguía libre. Si dos canjes compiten, el segundo falla.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from db.models import License
from services import session_scope
from services import subscriptions

# Alfabeto sin caracteres ambiguos (0/O, 1/I/L).
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class RedeemError(Exception):
    """Error de canje con mensaje apto para el usuario."""


def _gen_code() -> str:
    """Código tipo GEST-XXXX-XXXX-XXXX."""
    blocks = ["".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "GEST-" + "-".join(blocks)


async def create_licenses(count: int, days: int, created_by: int) -> list[str]:
    """Crea N licencias y devuelve sus códigos."""
    codes: list[str] = []
    async with session_scope() as s:
        for _ in range(count):
            # Reintentar si por casualidad colisiona el código.
            for _try in range(5):
                code = _gen_code()
                exists = await s.execute(select(License.id).where(License.code == code))
                if exists.scalar_one_or_none() is None:
                    break
            s.add(License(code=code, days=days, created_by=created_by))
            codes.append(code)
    return codes


async def redeem(code: str, user_id: int, group_id: int) -> dict:
    """Canjea un código para activar Premium en un grupo.

    Lanza RedeemError con un mensaje claro si no es válido.
    """
    code = (code or "").strip().upper()
    if not code:
        raise RedeemError("Debes indicar un código. Uso: /redeem CODIGO")

    async with session_scope() as s:
        res = await s.execute(select(License).where(License.code == code))
        lic = res.scalar_one_or_none()
        if lic is None:
            raise RedeemError("❌ Código no válido.")
        if lic.revoked:
            raise RedeemError("❌ Este código fue revocado.")
        if lic.redeemed:
            raise RedeemError("❌ Este código ya fue canjeado.")

        # Si el grupo ya tiene Premium activo, no permitir canjear otro.
        if await subscriptions.is_premium(group_id):
            raise RedeemError("💎 Este grupo ya tiene Premium activo. "
                              "Guarda el código para cuando expire.")

        # Marcar canjeado dentro de la misma transacción (anti-doble-canje).
        lic.redeemed = True
        lic.redeemed_by = user_id
        lic.redeemed_group = group_id
        lic.redeemed_at = datetime.now(timezone.utc)
        days = lic.days

    # Activar Premium (transacción aparte; el código ya quedó consumido).
    sub = await subscriptions.activate_premium(
        group_id, days=days, source="license", activated_by=user_id, auto_renew=False
    )
    return {"days": days, "subscription": sub}


async def revoke(code: str) -> bool:
    """Revoca una licencia no canjeada. True si se revocó."""
    code = (code or "").strip().upper()
    async with session_scope() as s:
        res = await s.execute(select(License).where(License.code == code))
        lic = res.scalar_one_or_none()
        if lic is None or lic.redeemed:
            return False
        lic.revoked = True
        return True


async def list_recent(limit: int = 20) -> list[dict]:
    async with session_scope() as s:
        res = await s.execute(
            select(License).order_by(License.id.desc()).limit(limit)
        )
        return [
            {
                "code": l.code, "days": l.days, "redeemed": l.redeemed,
                "redeemed_by": l.redeemed_by, "revoked": l.revoked,
            }
            for l in res.scalars()
        ]
