"""Decoradores de permisos para handlers de Telegram."""
from __future__ import annotations

import functools

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

import config


def admin_only(func):
    """Solo administradores del PRODUCTO (ADMIN_IDS del .env)."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **k):
        user = update.effective_user
        if not user or not config.is_admin(user.id):
            if update.effective_message:
                await update.effective_message.reply_text("🔒 Comando solo para el administrador del bot.")
            return
        return await func(update, context, *a, **k)
    return wrapper


def group_admin_only(func):
    """Solo administradores del GRUPO de Telegram."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **k):
        chat = update.effective_chat
        user = update.effective_user
        msg = update.effective_message
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            if msg:
                await msg.reply_text("⚠️ Este comando solo funciona en grupos.")
            return
        # Los admins del producto siempre pueden.
        if config.is_admin(user.id):
            return await func(update, context, *a, **k)
        try:
            member = await chat.get_member(user.id)
            if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                await msg.reply_text("🔒 Solo administradores del grupo.")
                return
        except Exception:  # noqa: BLE001
            await msg.reply_text("No pude verificar tus permisos.")
            return
        return await func(update, context, *a, **k)
    return wrapper
