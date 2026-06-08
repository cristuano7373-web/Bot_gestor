"""Utilidades compartidas por los handlers."""
from __future__ import annotations

import functools
from html import escape

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from services import subscriptions


def display_name(user) -> str:
    if user is None:
        return "usuario"
    return f"@{user.username}" if user.username else (user.full_name or "usuario")


def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{escape(name or "usuario")}</a>'


def is_group(chat) -> bool:
    return chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def resolve_target(update: Update):
    """(user_id, nombre) del objetivo: por respuesta o por @usuario/ID."""
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, display_name(u)
    args = msg.text.split()[1:] if msg.text else []
    if args:
        a = args[0]
        if a.lstrip("-").isdigit():
            return int(a), a
    return None


def premium_only(feature: str = "Esta función"):
    """Decorador: exige Premium activo en el grupo para usar el handler."""
    def deco(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **k):
            chat = update.effective_chat
            if is_group(chat) and not await subscriptions.is_premium(chat.id):
                await update.effective_message.reply_text(
                    f"💎 *{feature} es Premium.*\n"
                    "Actívalo con /premium o canjea una licencia con /redeem CODIGO.",
                    parse_mode="Markdown",
                )
                return
            return await func(update, context, *a, **k)
        return wrapper
    return deco
