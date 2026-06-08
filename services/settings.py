"""Configuración por grupo (clave/valor) con valores por defecto."""
from __future__ import annotations

from sqlalchemy import select

from db.models import GroupSettings
from services import session_scope

DEFAULTS: dict[str, object] = {
    "welcome_enabled": 1,
    "welcome_text": "👋 ¡Bienvenido/a {nombre} a {grupo}! Lee las /reglas.",
    "goodbye_enabled": 0,
    "rules_text": "",
    "warn_limit": 3,
    "warn_action": "mute",          # mute | kick | ban
    "antiflood_enabled": 1,
    "antiflood_count": 6,
    "antiflood_seconds": 7,
    "antilinks_enabled": 0,
    "antibadwords_enabled": 0,
    # --- Premium ---
    "ai_moderation": 0,
    "levels_enabled": 0,
    "captcha_enabled": 0,           # verificación anti-bots al entrar
    "captcha_timeout": 60,          # segundos para verificarse
    "faq_enabled": 0,               # respuestas automáticas
    "nightmode_enabled": 0,         # cierre nocturno del grupo
    "nightmode_start": 23,          # hora (0-23) de cierre
    "nightmode_end": 7,             # hora (0-23) de apertura
    "fedban_enabled": 0,            # aplicar lista negra global
}

TOGGLES = {
    "welcome_enabled": "👋 Bienvenidas",
    "goodbye_enabled": "🚪 Despedidas",
    "antiflood_enabled": "🌊 Antiflood",
    "antilinks_enabled": "🔗 Anti-enlaces",
    "antibadwords_enabled": "🚫 Anti-palabras",
    "captcha_enabled": "🤖 CAPTCHA anti-bots 💎",
    "ai_moderation": "🧠 Moderación IA 💎",
    "faq_enabled": "💬 Auto-respuestas 💎",
    "levels_enabled": "🎖️ Niveles 💎",
    "nightmode_enabled": "🌙 Modo nocturno 💎",
    "fedban_enabled": "🛡️ Lista negra global 💎",
}

PREMIUM_KEYS = {
    "ai_moderation", "levels_enabled", "captcha_enabled", "faq_enabled",
    "nightmode_enabled", "fedban_enabled",
}


def _coerce(key, value):
    d = DEFAULTS.get(key)
    if isinstance(d, int) and not isinstance(d, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return d
    return value if value is not None else d


async def get_all(group_id: int) -> dict:
    async with session_scope() as s:
        res = await s.execute(
            select(GroupSettings).where(GroupSettings.group_id == group_id))
        out = dict(DEFAULTS)
        for row in res.scalars():
            out[row.key] = _coerce(row.key, row.value)
        return out


async def get(group_id: int, key: str):
    async with session_scope() as s:
        res = await s.execute(
            select(GroupSettings).where(
                GroupSettings.group_id == group_id, GroupSettings.key == key))
        row = res.scalar_one_or_none()
        return _coerce(key, row.value) if row else DEFAULTS.get(key)


async def set(group_id: int, key: str, value) -> None:
    async with session_scope() as s:
        res = await s.execute(
            select(GroupSettings).where(
                GroupSettings.group_id == group_id, GroupSettings.key == key))
        row = res.scalar_one_or_none()
        if row is None:
            s.add(GroupSettings(group_id=group_id, key=key, value=str(value)))
        else:
            row.value = str(value)


async def toggle(group_id: int, key: str) -> int:
    current = await get(group_id, key)
    new_val = 0 if int(current or 0) else 1
    await set(group_id, key, new_val)
    return new_val
