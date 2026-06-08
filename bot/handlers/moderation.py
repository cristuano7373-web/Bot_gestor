"""Moderación: comandos (mute/kick/ban/warn) y automod de mensajes."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from telegram import ChatPermissions, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ContextTypes

import config
from bot.common import is_group, mention, resolve_target, display_name
from security.permissions import group_admin_only
from services import session_scope, settings, stats, subscriptions
from services.entities import audit
from db.models import Warn
from moderation import ai
from moderation.filters import flood_tracker, has_link, contains_badword, is_spam

_MUTED = ChatPermissions(can_send_messages=False)
_UNMUTED = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_send_polls=True,
)


async def _is_admin(chat, uid) -> bool:
    if config.is_admin(uid):
        return True
    try:
        m = await chat.get_member(uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:  # noqa: BLE001
        return False


# ----------------------- Comandos -----------------------
@group_admin_only
async def cmd_ban(update, context):
    t = await resolve_target(update)
    if not t:
        await update.effective_message.reply_text("Responde a un usuario o usa /ban ID.")
        return
    uid, name = t
    if await _is_admin(update.effective_chat, uid):
        await update.effective_message.reply_text("🛡️ No puedo banear a un administrador.")
        return
    try:
        await update.effective_chat.ban_member(uid)
        await audit(update.effective_user.id, "ban", f"{uid}@{update.effective_chat.id}")
        await update.effective_message.reply_text(f"🔨 {mention(uid, name)} baneado.",
                                                   parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ No pude banear: {e}")


@group_admin_only
async def cmd_kick(update, context):
    t = await resolve_target(update)
    if not t:
        await update.effective_message.reply_text("Responde a un usuario o usa /kick ID.")
        return
    uid, name = t
    if await _is_admin(update.effective_chat, uid):
        await update.effective_message.reply_text("🛡️ No puedo expulsar a un administrador.")
        return
    try:
        await update.effective_chat.ban_member(uid)
        await update.effective_chat.unban_member(uid, only_if_banned=True)
        await update.effective_message.reply_text(f"👢 {mention(uid, name)} expulsado.",
                                                   parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ No pude expulsar: {e}")


@group_admin_only
async def cmd_mute(update, context):
    t = await resolve_target(update)
    if not t:
        await update.effective_message.reply_text("Responde a un usuario o usa /mute ID [minutos].")
        return
    uid, name = t
    if await _is_admin(update.effective_chat, uid):
        await update.effective_message.reply_text("🛡️ No puedo silenciar a un administrador.")
        return
    minutes = 0
    for a in (context.args or []):
        if a.isdigit():
            minutes = int(a)
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes) if minutes else None
    try:
        await update.effective_chat.restrict_member(uid, permissions=_MUTED, until_date=until)
        extra = f" por {minutes} min" if minutes else ""
        await update.effective_message.reply_text(
            f"🔇 {mention(uid, name)} silenciado{extra}.", parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ No pude silenciar: {e}")


@group_admin_only
async def cmd_unmute(update, context):
    t = await resolve_target(update)
    if not t:
        await update.effective_message.reply_text("Responde a un usuario o usa /unmute ID.")
        return
    uid, name = t
    try:
        await update.effective_chat.restrict_member(uid, permissions=_UNMUTED)
        await update.effective_message.reply_text(
            f"🔊 {mention(uid, name)} puede hablar de nuevo.", parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ No pude reactivar: {e}")


@group_admin_only
async def cmd_warn(update, context):
    t = await resolve_target(update)
    if not t:
        await update.effective_message.reply_text("Responde a un usuario o usa /warn ID [motivo].")
        return
    uid, name = t
    if await _is_admin(update.effective_chat, uid):
        await update.effective_message.reply_text("🛡️ No puedo advertir a un administrador.")
        return
    reason = " ".join(a for a in (context.args or []) if not a.isdigit()) or "—"
    count, limit, action = await _add_warn(update.effective_chat.id, uid, reason)
    if count >= limit:
        await _apply_action(update, uid, name, action)
        await _reset_warn(update.effective_chat.id, uid)
    else:
        await update.effective_message.reply_text(
            f"⚠️ {mention(uid, name)} advertido ({count}/{limit}).",
            parse_mode=ParseMode.HTML)


async def _add_warn(group_id, uid, reason):
    async with session_scope() as s:
        res = await s.execute(select(Warn).where(
            Warn.group_id == group_id, Warn.user_id == uid))
        w = res.scalar_one_or_none()
        if w is None:
            w = Warn(group_id=group_id, user_id=uid, count=0, reasons="[]")
            s.add(w)
        w.count += 1
        reasons = json.loads(w.reasons or "[]")
        reasons.append(reason)
        w.reasons = json.dumps(reasons)
        count = w.count
    cfg = await settings.get_all(group_id)
    return count, int(cfg["warn_limit"]), cfg["warn_action"]


async def _reset_warn(group_id, uid):
    async with session_scope() as s:
        res = await s.execute(select(Warn).where(
            Warn.group_id == group_id, Warn.user_id == uid))
        w = res.scalar_one_or_none()
        if w:
            w.count = 0
            w.reasons = "[]"


async def _apply_action(update, uid, name, action):
    chat = update.effective_chat
    try:
        if action == "ban":
            await chat.ban_member(uid); verb = "baneado 🔨"
        elif action == "kick":
            await chat.ban_member(uid); await chat.unban_member(uid, only_if_banned=True)
            verb = "expulsado 👢"
        else:
            await chat.restrict_member(uid, permissions=_MUTED); verb = "silenciado 🔇"
        await update.effective_message.reply_text(
            f"🚷 {mention(uid, name)} alcanzó el límite y fue {verb}.",
            parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"Límite alcanzado, pero falló la acción: {e}")


# ----------------------- Automod (cada mensaje) -----------------------
async def automod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not is_group(chat) or user is None or msg is None:
        return

    text = msg.text or msg.caption or ""

    # 1) Estadísticas (siempre)
    await stats.record_message(chat.id, user.id)

    cfg = await settings.get_all(chat.id)
    premium = await subscriptions.is_premium(chat.id)

    # 1b) Auto-respuestas / FAQ (Premium) — responde a todos
    if premium and cfg.get("faq_enabled") and text:
        from services import faq
        answer = await faq.match(chat.id, text)
        if answer:
            try:
                await msg.reply_text(answer)
            except Exception:  # noqa: BLE001
                pass

    # Los admins quedan exentos de los filtros.
    if await _is_admin(chat, user.id):
        return

    # 2) Niveles (Premium) con anuncio de ascenso
    if premium and cfg.get("levels_enabled"):
        leveled, new_level = await _add_xp(chat.id, user.id)
        if leveled:
            try:
                await msg.reply_text(
                    f"🎖️ {mention(user.id, display_name(user))} subió al "
                    f"*nivel {new_level}*. ¡Sigue así! ✨", parse_mode=ParseMode.HTML)
            except Exception:  # noqa: BLE001
                pass

    # 3) Antiflood
    if cfg.get("antiflood_enabled"):
        if flood_tracker.hit(chat.id, user.id, count=int(cfg["antiflood_count"]),
                             window=float(cfg["antiflood_seconds"])):
            try:
                await chat.restrict_member(user.id, permissions=_MUTED)
                await msg.reply_text(
                    f"🌊 {mention(user.id, display_name(user))} silenciado por flood.",
                    parse_mode=ParseMode.HTML)
            except Exception:  # noqa: BLE001
                pass
            return

    # 4) Anti-enlaces
    if cfg.get("antilinks_enabled") and has_link(text, msg.entities):
        await _delete(msg)
        return

    # 5) Anti-palabras (lista en settings: badwords como CSV)
    if cfg.get("antibadwords_enabled"):
        words = (await settings.get(chat.id, "badwords_list") or "")
        if isinstance(words, str) and words:
            if contains_badword(text, words.split(",")):
                await _delete(msg)
                return

    # 6) Antispam básico
    if is_spam(text):
        await _delete(msg)
        return

    # 7) Moderación con IA (Premium)
    if premium and cfg.get("ai_moderation") and text:
        result = ai.classify(text)
        if ai.should_act(result, threshold=0.6):
            await _delete(msg)
            try:
                await context.bot.send_message(
                    chat.id,
                    f"🧠 Mensaje de {display_name(user)} eliminado por IA "
                    f"({result['reason']}).")
            except Exception:  # noqa: BLE001
                pass


async def _add_xp(group_id, uid):
    """Suma XP y devuelve (subió_de_nivel, nuevo_nivel)."""
    from db.models import UserLevel
    leveled = False
    new_level = 1
    async with session_scope() as s:
        res = await s.execute(select(UserLevel).where(
            UserLevel.group_id == group_id, UserLevel.user_id == uid))
        lv = res.scalar_one_or_none()
        if lv is None:
            lv = UserLevel(group_id=group_id, user_id=uid, xp=0, level=1)
            s.add(lv)
        lv.xp += 5
        needed = lv.level * 100
        if lv.xp >= needed:
            lv.xp -= needed
            lv.level += 1
            leveled = True
        new_level = lv.level
    return leveled, new_level


async def _delete(msg):
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        pass
