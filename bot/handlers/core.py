"""Núcleo: inicio, ayuda, panel de ajustes, bienvenidas, reglas, stats y export."""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import config
from bot.common import is_group, mention, premium_only
from security.permissions import group_admin_only
from services import faq, federation, settings, stats, subscriptions
from services.entities import ensure_group, ensure_user


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await ensure_user(user.id, user.username, user.first_name)
    if is_group(update.effective_chat):
        await ensure_group(update.effective_chat.id, update.effective_chat.title)
        await update.effective_message.reply_text(
            "🤖 *Bot_Gestor* activo.\nAdmins: abran el /panel para configurar. "
            "Vean /premium para desbloquear todo. 💎",
            parse_mode=ParseMode.MARKDOWN)
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Añadir a un grupo",
                              url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("💎 Ver Premium", callback_data="show_premium")],
    ])
    await update.effective_message.reply_text(
        "🤖 *Bot_Gestor*\n"
        "_Administra tu grupo como un profesional._\n"
        "━━━━━━━━━━━━━━━\n"
        "Moderación automática, bienvenidas, estadísticas, niveles, IA y más.\n\n"
        "Añádeme a tu grupo y hazme administrador para empezar.",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📖 *Guía de Bot_Gestor*\n"
        "═══════════════\n\n"
        "🛡️ *Moderación*\n"
        "/ban · /kick · /mute · /unmute · /warn\n\n"
        "⚙️ *Configuración* (admins)\n"
        "/panel · todo con botones\n"
        "/setbienvenida · /setreglas · /reglas\n\n"
        "📊 *Estadísticas*\n"
        "/stats · actividad y ranking\n\n"
        "💎 *Premium*\n"
        "/premium · ver y activar\n"
        "/faq palabra | respuesta · auto-respuestas\n"
        "/programar 18:30 | texto · mensajes programados\n"
        "/nochehoras 23 7 · modo nocturno\n"
        "/fban · lista negra global\n"
        "/nivel · tu nivel · /reporte · export CSV\n\n"
        "_Activa cada función desde el /panel._",
        parse_mode=ParseMode.MARKDOWN)


# ----------------------- Panel de ajustes -----------------------
@group_admin_only
async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_group(update.effective_chat.id, update.effective_chat.title)
    cfg = await settings.get_all(update.effective_chat.id)
    premium = await subscriptions.is_premium(update.effective_chat.id)
    await update.effective_message.reply_text(
        _panel_text(update.effective_chat.title, cfg, premium),
        parse_mode=ParseMode.MARKDOWN, reply_markup=_panel_kb(cfg))


def _panel_text(title, cfg, premium) -> str:
    plan = "💎 *Premium activo*" if premium else "🆓 Plan Gratis"
    return (f"⚙️ *Panel · {title or 'grupo'}*\n"
            f"═══════════════\n"
            f"{plan}\n"
            f"⚠️ Avisos: {cfg['warn_limit']} → {cfg['warn_action']}    "
            f"🌊 Flood: {cfg['antiflood_count']}/{cfg['antiflood_seconds']}s\n\n"
            "Toca para activar ✅ o desactivar ⬜.\n"
            "Las marcadas con 💎 requieren Premium.")


def _panel_kb(cfg) -> InlineKeyboardMarkup:
    free_keys = ["welcome_enabled", "goodbye_enabled", "antiflood_enabled",
                 "antilinks_enabled", "antibadwords_enabled"]
    premium_keys = ["captcha_enabled", "ai_moderation", "faq_enabled",
                    "levels_enabled", "nightmode_enabled", "fedban_enabled"]

    def row(key):
        mark = "✅" if int(cfg.get(key, 0) or 0) else "⬜"
        return [InlineKeyboardButton(f"{mark} {settings.TOGGLES[key]}",
                                     callback_data=f"tg:{key}")]

    rows = [[InlineKeyboardButton("──  🛡️ GRATIS  ──", callback_data="noop")]]
    rows += [row(k) for k in free_keys]
    rows.append([InlineKeyboardButton("──  💎 PREMIUM  ──", callback_data="noop")])
    rows += [row(k) for k in premium_keys]
    return InlineKeyboardMarkup(rows)


async def cb_noop(update, context):
    await update.callback_query.answer()


async def cb_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    chat = update.effective_chat
    # Permisos: admin del grupo
    if not config.is_admin(query.from_user.id):
        try:
            m = await chat.get_member(query.from_user.id)
            from telegram.constants import ChatMemberStatus
            if m.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                await query.answer("Solo administradores.", show_alert=True)
                return
        except Exception:  # noqa: BLE001
            await query.answer("No pude verificar permisos.", show_alert=True)
            return
    # Las funciones Premium requieren suscripción.
    if key in settings.PREMIUM_KEYS and not await subscriptions.is_premium(chat.id):
        await query.answer("💎 Función Premium. Actívala con /premium.", show_alert=True)
        return
    await settings.toggle(chat.id, key)
    await query.answer("Actualizado ✅")
    cfg = await settings.get_all(chat.id)
    premium = await subscriptions.is_premium(chat.id)
    try:
        await query.edit_message_text(
            _panel_text(chat.title, cfg, premium),
            parse_mode=ParseMode.MARKDOWN, reply_markup=_panel_kb(cfg))
    except BadRequest:
        pass


# ----------------------- Reglas y bienvenida -----------------------
@group_admin_only
async def cmd_setrules(update, context):
    text = " ".join(context.args or [])
    if not text and update.effective_message.reply_to_message:
        text = update.effective_message.reply_to_message.text or ""
    if not text:
        await update.effective_message.reply_text("Uso: /setreglas <texto>")
        return
    await settings.set(update.effective_chat.id, "rules_text", text)
    await update.effective_message.reply_text("📜 Reglas guardadas.")


async def cmd_rules(update, context):
    if not is_group(update.effective_chat):
        return
    text = await settings.get(update.effective_chat.id, "rules_text")
    await update.effective_message.reply_text(
        f"📜 *Reglas*\n\n{text}" if text else "ℹ️ Sin reglas. Un admin: /setreglas.",
        parse_mode=ParseMode.MARKDOWN)


@group_admin_only
async def cmd_setwelcome(update, context):
    text = " ".join(context.args or [])
    if not text:
        await update.effective_message.reply_text(
            "Uso: /setbienvenida <texto>\nVariables: {nombre}, {grupo}")
        return
    await settings.set(update.effective_chat.id, "welcome_text", text)
    await update.effective_message.reply_text("👋 Bienvenida actualizada.")


async def _safe_send(context, chat_id: int, text: str, **kwargs) -> bool:
    """Envía un mensaje ignorando que el bot fuera expulsado o no tenga permiso.

    Si el bot ya no puede escribir en el grupo, lo marca como inactivo.
    Devuelve True si se envió.
    """
    try:
        await context.bot.send_message(chat_id, text, **kwargs)
        return True
    except Forbidden:
        # Bot expulsado o sin permiso: desactivar el grupo en BD.
        try:
            from services import session_scope
            from db.models import Group
            async with session_scope() as s:
                g = await s.get(Group, chat_id)
                if g:
                    g.is_active = False
        except Exception:  # noqa: BLE001
            pass
        return False
    except Exception:  # noqa: BLE001
        return False


_CAPTCHA_MUTE = ChatPermissions(can_send_messages=False)


async def on_new_member(update, context):
    msg = update.effective_message
    chat = update.effective_chat
    cfg = await settings.get_all(chat.id)
    premium = await subscriptions.is_premium(chat.id)
    bot_id = context.bot.id

    # Dueño del grupo (para federación)
    from services import session_scope
    from db.models import Group
    owner_id = None
    async with session_scope() as s:
        g = await s.get(Group, chat.id)
        owner_id = g.added_by if g else None

    for m in msg.new_chat_members or []:
        if m.id == bot_id:
            await ensure_group(chat.id, chat.title, update.effective_user.id)
            await _safe_send(
                context, chat.id, "🤖 *Bot_Gestor* listo. Hazme admin y abre /panel.",
                parse_mode=ParseMode.MARKDOWN)
            continue

        # 🛡️ Lista negra global: banear al entrar si está vetado
        if premium and cfg.get("fedban_enabled") and owner_id:
            if await federation.is_banned(owner_id, m.id):
                try:
                    await chat.ban_member(m.id)
                    await _safe_send(context, chat.id,
                                     f"🛡️ {m.full_name} está en la lista negra global. Baneado.")
                except Exception:  # noqa: BLE001
                    pass
                continue

        await stats.record_message(chat.id, m.id, new_member=True)

        # 🤖 CAPTCHA anti-bots (Premium)
        if premium and cfg.get("captcha_enabled"):
            await _start_captcha(context, chat, m, int(cfg.get("captcha_timeout", 60)))
            continue

        # 👋 Bienvenida normal
        if cfg.get("welcome_enabled"):
            text = (cfg.get("welcome_text") or "👋 ¡Bienvenido {nombre}!") \
                .replace("{nombre}", m.full_name).replace("{grupo}", chat.title or "el grupo")
            await _safe_send(context, chat.id, text)


async def _start_captcha(context, chat, member, timeout: int) -> None:
    """Silencia al nuevo miembro y le pide verificarse con un botón."""
    try:
        await chat.restrict_member(member.id, permissions=_CAPTCHA_MUTE)
    except Exception:  # noqa: BLE001
        return
    pending = context.application.bot_data.setdefault("captcha", set())
    pending.add((chat.id, member.id))
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "✅ Soy humano", callback_data=f"captcha:{chat.id}:{member.id}")]])
    sent = None
    try:
        sent = await context.bot.send_message(
            chat.id,
            f"🤖 {mention(member.id, member.full_name)}, verifícate pulsando el botón "
            f"en {timeout}s o serás expulsado.",
            parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:  # noqa: BLE001
        pass
    if context.job_queue:
        context.job_queue.run_once(
            _captcha_timeout, when=timeout,
            data={"chat_id": chat.id, "user_id": member.id,
                  "msg_id": sent.message_id if sent else None},
            name=f"captcha_{chat.id}_{member.id}")


async def _captcha_timeout(context: ContextTypes.DEFAULT_TYPE) -> None:
    d = context.job.data
    pending = context.application.bot_data.setdefault("captcha", set())
    key = (d["chat_id"], d["user_id"])
    if key not in pending:
        return   # ya se verificó
    pending.discard(key)
    try:
        await context.bot.ban_chat_member(d["chat_id"], d["user_id"])
        await context.bot.unban_chat_member(d["chat_id"], d["user_id"], only_if_banned=True)
        if d.get("msg_id"):
            await context.bot.delete_message(d["chat_id"], d["msg_id"])
    except Exception:  # noqa: BLE001
        pass


async def cb_captcha(update, context):
    query = update.callback_query
    _, chat_id_s, uid_s = query.data.split(":")
    chat_id, uid = int(chat_id_s), int(uid_s)
    if query.from_user.id != uid:
        await query.answer("Este botón no es para ti 🙂", show_alert=True)
        return
    pending = context.application.bot_data.setdefault("captcha", set())
    pending.discard((chat_id, uid))
    from bot.handlers.features import _OPEN
    try:
        await context.bot.restrict_chat_member(chat_id, uid, permissions=_OPEN)
    except Exception:  # noqa: BLE001
        pass
    await query.answer("¡Verificado! ✅")
    cfg = await settings.get_all(chat_id)
    name = query.from_user.full_name
    text = (cfg.get("welcome_text") or "👋 ¡Bienvenido {nombre}!") \
        .replace("{nombre}", name).replace("{grupo}", query.message.chat.title or "el grupo")
    try:
        await query.edit_message_text(f"✅ {name} verificado.\n\n{text}")
    except BadRequest:
        pass


async def on_left_member(update, context):
    chat = update.effective_chat
    cfg = await settings.get_all(chat.id)
    left = update.effective_message.left_chat_member
    if cfg.get("goodbye_enabled") and left and left.id != context.bot.id:
        await _safe_send(context, chat.id, f"👋 {left.full_name} salió del grupo.")


# ----------------------- Estadísticas -----------------------
async def cmd_stats(update, context):
    if not is_group(update.effective_chat):
        await update.effective_message.reply_text("Usa /stats dentro de un grupo.")
        return
    chat = update.effective_chat
    summ = await stats.group_summary(chat.id, days=7)
    rank = await stats.ranking(chat.id, days=7, limit=5)
    series = stats.daily_series(summ, 7)
    spark = _sparkline([v for _, v in series])
    lines = [
        f"📊 *Estadísticas (7 días)* · {chat.title or ''}",
        "━━━━━━━━━━━━━━━",
        f"💬 Mensajes: {summ['total_messages']}",
        f"👥 Usuarios activos: {summ['active_users']}",
        f"🆕 Nuevos miembros: {summ['new_members']}",
        f"📈 Actividad: {spark}",
    ]
    if rank:
        lines.append("\n🏆 *Top activos:*")
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, r in enumerate(rank):
            lines.append(f"{medals[i]} `{r['user_id']}` — {r['messages']} msg")
    lines.append("\n💎 Reportes y export CSV/Excel: /reporte (Premium)")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


def _sparkline(values) -> str:
    if not values or max(values) == 0:
        return "▁" * len(values)
    blocks = "▁▂▃▄▅▆▇█"
    mx = max(values)
    return "".join(blocks[min(7, int(v / mx * 7))] for v in values)


# ----------------------- Premium: reporte + export -----------------------
@premium_only("Los reportes con exportación")
async def cmd_report(update, context):
    chat = update.effective_chat
    period = (context.args[0].lower() if context.args else "semanal")
    days = 30 if period.startswith("mes") else 7
    summ = await stats.group_summary(chat.id, days=days)
    rank = await stats.ranking(chat.id, days=days, limit=50)

    # Generar CSV
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user_id", "mensajes"])
    for r in rank:
        w.writerow([r["user_id"], r["messages"]])
    data = io.BytesIO(buf.getvalue().encode("utf-8"))
    data.name = f"reporte_{chat.id}_{days}d.csv"

    await update.effective_message.reply_document(
        document=data, filename=data.name,
        caption=(f"📈 *Reporte {days} días*\n"
                 f"💬 {summ['total_messages']} mensajes · "
                 f"👥 {summ['active_users']} activos · "
                 f"🆕 {summ['new_members']} nuevos"),
        parse_mode=ParseMode.MARKDOWN)


@premium_only("El sistema de niveles")
async def cmd_level(update, context):
    from sqlalchemy import select
    from db.models import UserLevel
    from services import session_scope
    chat = update.effective_chat
    uid = update.effective_user.id
    async with session_scope() as s:
        res = await s.execute(select(UserLevel).where(
            UserLevel.group_id == chat.id, UserLevel.user_id == uid))
        lv = res.scalar_one_or_none()
    if not lv:
        await update.effective_message.reply_text("Aún no tienes XP. ¡Participa! 💬")
        return
    needed = lv.level * 100
    await update.effective_message.reply_text(
        f"🎖️ *Tu nivel:* {lv.level}\n✨ XP: {lv.xp}/{needed}",
        parse_mode=ParseMode.MARKDOWN)


async def cb_show_premium(update, context):
    from bot.handlers.premium import PREMIUM_INFO, HOW_TO_ACTIVATE
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        PREMIUM_INFO + HOW_TO_ACTIVATE, parse_mode=ParseMode.MARKDOWN)
