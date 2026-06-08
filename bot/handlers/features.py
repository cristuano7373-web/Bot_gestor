"""Funciones Premium avanzadas: auto-respuestas (FAQ), mensajes programados,
modo nocturno y federación (lista negra global)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import ChatPermissions, Update
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes

import config
from bot.common import is_group, mention, resolve_target, premium_only
from security.permissions import group_admin_only
from services import faq, federation, schedules, settings
from services.entities import audit
from moderation.nightmode import is_night

log = logging.getLogger("bot_gestor")

_CLOSED = ChatPermissions(can_send_messages=False)
_OPEN = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_send_polls=True)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(config.TIMEZONE)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


# ===================== FAQ / Auto-respuestas =====================
@premium_only("Las auto-respuestas")
@group_admin_only
async def cmd_faq_add(update, context):
    raw = " ".join(context.args or [])
    if "|" not in raw:
        await update.effective_message.reply_text(
            "Uso: /faq palabra | respuesta\nEj: /faq horario | Atendemos de 9 a 18h")
        return
    kw, ans = (p.strip() for p in raw.split("|", 1))
    if not kw or not ans:
        await update.effective_message.reply_text("Faltan datos. /faq palabra | respuesta")
        return
    await faq.set_entry(update.effective_chat.id, kw, ans)
    await settings.set(update.effective_chat.id, "faq_enabled", 1)
    await update.effective_message.reply_text(
        f"💬 Auto-respuesta creada para *{kw.lower()}*.", parse_mode=ParseMode.MARKDOWN)


@group_admin_only
async def cmd_faq_del(update, context):
    if not context.args:
        await update.effective_message.reply_text("Uso: /faqdel palabra")
        return
    ok = await faq.delete(update.effective_chat.id, context.args[0])
    await update.effective_message.reply_text("🗑️ Eliminada." if ok else "No existe.")


async def cmd_faq_list(update, context):
    if not is_group(update.effective_chat):
        return
    rows = await faq.list_for(update.effective_chat.id)
    if not rows:
        await update.effective_message.reply_text("📭 Sin auto-respuestas.")
        return
    txt = "\n".join(f"• {r['keyword']}" for r in rows)
    await update.effective_message.reply_text(
        f"💬 *Auto-respuestas*\n{txt}", parse_mode=ParseMode.MARKDOWN)


# ===================== Mensajes programados =====================
def _parse_when(s: str):
    """Devuelve ('once', datetime) o ('interval', segundos) o None."""
    s = s.strip().lower()
    m = re.match(r"^(\d+)\s*(m|min|h|d)$", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        secs = n * (60 if u.startswith("m") else 3600 if u == "h" else 86400)
        return ("interval", secs)
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        tz = _tz()
        now = datetime.now(tz)
        dt = now.replace(hour=int(m.group(1)), minute=int(m.group(2)),
                         second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        return ("once", dt.astimezone(timezone.utc))
    return None


@premium_only("Los mensajes programados")
@group_admin_only
async def cmd_schedule(update, context):
    raw = " ".join(context.args or [])
    if "|" not in raw:
        await update.effective_message.reply_text(
            "⏰ *Programar mensaje*\n"
            "Uso: `/programar CUANDO | TEXTO`\n"
            "• `/programar 18:30 | Reunión!` (una vez)\n"
            "• `/programar 6h | Lean las reglas` (cada 6 horas)\n"
            "• `/programar 1d | Resumen diario` (cada día)",
            parse_mode=ParseMode.MARKDOWN)
        return
    when_s, text = (p.strip() for p in raw.split("|", 1))
    parsed = _parse_when(when_s)
    if not parsed or not text:
        await update.effective_message.reply_text("Formato no válido. Usa HH:MM o 6h/1d.")
        return
    kind, val = parsed
    run_at = val if kind == "once" else None
    interval = val if kind == "interval" else None
    sid = await schedules.add(update.effective_chat.id, text, run_at=run_at,
                              interval_s=interval, created_by=update.effective_user.id)
    row = await schedules.get(sid)
    _schedule_job(context.application, row)
    cuando = ("una vez" if kind == "once" else f"cada {when_s}")
    await update.effective_message.reply_text(
        f"✅ Programado #{sid} ({cuando}).", parse_mode=ParseMode.MARKDOWN)


@group_admin_only
async def cmd_schedules(update, context):
    rows = await schedules.list_for(update.effective_chat.id)
    if not rows:
        await update.effective_message.reply_text("📭 No hay mensajes programados.")
        return
    lines = ["⏰ *Programados*"]
    for r in rows:
        prev = (r["text"][:30] + "…") if len(r["text"]) > 30 else r["text"]
        cuando = f"cada {r['interval_s']//3600}h" if r["interval_s"] else (r["run_at"] or "")[:16]
        lines.append(f"#{r['id']} · {cuando} · {prev}")
    lines.append("\nCancelar: /cancelprog <id>")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@group_admin_only
async def cmd_cancel_schedule(update, context):
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Uso: /cancelprog <id>")
        return
    sid = int(context.args[0])
    ok = await schedules.deactivate(sid, update.effective_chat.id)
    if ok and context.job_queue:
        for j in context.job_queue.get_jobs_by_name(f"sched_{sid}"):
            j.schedule_removal()
    await update.effective_message.reply_text("🗑️ Cancelado." if ok else "No encontrado.")


async def _fire_schedule(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.send_message(data["group_id"], f"📢 {data['text']}")
    except Exception:  # noqa: BLE001
        pass
    if data.get("once"):
        await schedules.deactivate(data["sched_id"])


def _schedule_job(app: Application, row: dict) -> None:
    jq = app.job_queue
    if jq is None or not row:
        return
    name = f"sched_{row['id']}"
    for j in jq.get_jobs_by_name(name):
        j.schedule_removal()
    data = {"group_id": row["group_id"], "text": row["text"],
            "sched_id": row["id"], "once": row["interval_s"] is None}
    if row["interval_s"]:
        jq.run_repeating(_fire_schedule, interval=row["interval_s"],
                         first=row["interval_s"], name=name, data=data)
    elif row["run_at"]:
        run_at = datetime.fromisoformat(row["run_at"])
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        if run_at > datetime.now(timezone.utc):
            jq.run_once(_fire_schedule, when=run_at, name=name, data=data)


async def restore_schedules(app: Application) -> None:
    rows = await schedules.all_active()
    n = 0
    for r in rows:
        if r["interval_s"] is None and r["run_at"]:
            if datetime.fromisoformat(r["run_at"]) <= datetime.now(timezone.utc):
                await schedules.deactivate(r["id"])
                continue
        _schedule_job(app, r)
        n += 1
    if n:
        log.info("Reprogramados %d mensajes.", n)


# ===================== Modo nocturno =====================
@premium_only("El modo nocturno")
@group_admin_only
async def cmd_setnight(update, context):
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit() or not args[1].isdigit():
        await update.effective_message.reply_text(
            "Uso: /nochehoras <inicio> <fin>  (0-23)\nEj: /nochehoras 23 7")
        return
    start, end = int(args[0]) % 24, int(args[1]) % 24
    await settings.set(update.effective_chat.id, "nightmode_start", start)
    await settings.set(update.effective_chat.id, "nightmode_end", end)
    await settings.set(update.effective_chat.id, "nightmode_enabled", 1)
    await update.effective_message.reply_text(
        f"🌙 Modo nocturno: cierre {start}:00 → apertura {end}:00.")


async def nightmode_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job periódico: cierra/abre grupos según su ventana nocturna."""
    from services import session_scope, subscriptions
    from db.models import Group
    from sqlalchemy import select
    state = context.application.bot_data.setdefault("night_state", {})
    hour = datetime.now(_tz()).hour
    async with session_scope() as s:
        res = await s.execute(select(Group.id).where(Group.is_active == True))  # noqa: E712
        group_ids = [g for g in res.scalars()]
    for gid in group_ids:
        cfg = await settings.get_all(gid)
        if not cfg.get("nightmode_enabled"):
            continue
        if not await subscriptions.is_premium(gid):
            continue
        night = is_night(hour, int(cfg["nightmode_start"]), int(cfg["nightmode_end"]))
        if state.get(gid) == night:
            continue
        start_h, end_h = int(cfg["nightmode_start"]), int(cfg["nightmode_end"])
        try:
            await context.bot.set_chat_permissions(gid, _CLOSED if night else _OPEN)
            if night:
                msg = (f"🌙 *Modo noche activado*\n"
                       f"De las *{start_h:02d}:00* a las *{end_h:02d}:00* no se "
                       f"podrán enviar mensajes.\n¡Feliz noche a todos! 😴💤")
            else:
                msg = ("☀️ *¡Buenos días!*\n"
                       "El grupo está abierto otra vez. ¡Ya pueden escribir! 💬")
            await context.bot.send_message(gid, msg, parse_mode=ParseMode.MARKDOWN)
            state[gid] = night
        except Exception:  # noqa: BLE001
            pass


# ===================== Federación (lista negra global) =====================
@premium_only("La lista negra global")
@group_admin_only
async def cmd_fban(update, context):
    t = await resolve_target(update)
    if not t:
        await update.effective_message.reply_text("Responde a un usuario o usa /fban ID [motivo].")
        return
    uid, name = t
    owner = update.effective_user.id
    reason = " ".join(a for a in (context.args or []) if not a.isdigit()) or None
    await federation.add_ban(owner, uid, reason)
    groups = await federation.owner_groups(owner)
    banned = 0
    for gid in groups:
        try:
            await context.bot.ban_chat_member(gid, uid)
            banned += 1
        except Exception:  # noqa: BLE001
            pass
    await audit(owner, "fban", f"{uid} en {banned} grupos")
    await update.effective_message.reply_text(
        f"🛡️ {mention(uid, name)} añadido a tu lista negra global "
        f"y baneado en {banned} grupo(s).", parse_mode=ParseMode.HTML)


@group_admin_only
async def cmd_unfban(update, context):
    t = await resolve_target(update)
    if not t:
        await update.effective_message.reply_text("Responde a un usuario o usa /unfban ID.")
        return
    uid, name = t
    owner = update.effective_user.id
    ok = await federation.remove_ban(owner, uid)
    for gid in await federation.owner_groups(owner):
        try:
            await context.bot.unban_chat_member(gid, uid, only_if_banned=True)
        except Exception:  # noqa: BLE001
            pass
    await update.effective_message.reply_text(
        "✅ Quitado de la lista negra." if ok else "No estaba en la lista.")


@group_admin_only
async def cmd_fbanlist(update, context):
    rows = await federation.list_bans(update.effective_user.id)
    if not rows:
        await update.effective_message.reply_text("Tu lista negra global está vacía.")
        return
    txt = "\n".join(f"• `{r['user_id']}` — {r['reason'] or 'sin motivo'}" for r in rows)
    await update.effective_message.reply_text(
        f"🛡️ *Lista negra global* ({len(rows)})\n{txt}", parse_mode=ParseMode.MARKDOWN)
