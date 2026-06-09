"""Panel de configuración en PRIVADO, todo por botones.

Idea: la configuración no se hace en el grupo (donde se pierde entre mensajes),
sino en el chat privado con el bot. Desde el grupo, un único botón abre el panel
en privado mediante un deep link. Toda la navegación edita el MISMO mensaje y los
ajustes de texto (bienvenida, reglas) se piden con flujos guiados.

callback_data: "dash:<accion>:<...>".
"""
from __future__ import annotations

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo,
)
from telegram.constants import ChatMemberStatus, ChatType, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import config
from bot.common import is_group
from bot import i18n
from services import settings, subscriptions, licenses
from services.entities import ensure_group, ensure_user, audit, get_lang, set_lang
from db.base import get_sessionmaker
from db.models import Group


# --------------------------------------------------------------------------- #
# Textos de onboarding (qué es el bot)
# --------------------------------------------------------------------------- #
INTRO = (
    "🤖 *Bot_Gestor*\n"
    "_El asistente que administra tu grupo por ti._\n"
    "═══════════════\n\n"
    "Yo me encargo de:\n"
    "🛡️ Frenar spam, flood, enlaces y bots\n"
    "👋 Dar la bienvenida a los nuevos\n"
    "📊 Mostrarte estadísticas del grupo\n"
    "🎖️ Premiar a los más activos con niveles\n"
    "⏰ Enviar mensajes programados\n"
    "💎 Y mucho más con Premium\n\n"
    "👇 Empieza configurando un grupo."
)

WHAT = (
    "❓ *¿Qué es Bot_Gestor?*\n"
    "═══════════════\n"
    "Es un bot para *administrar grupos de Telegram* de forma automática y fácil.\n\n"
    "*Cómo se usa en 3 pasos:*\n"
    "1️⃣ Me añades a tu grupo y me haces *administrador*.\n"
    "2️⃣ Escribes /config en el grupo y pulsas *Abrir panel*.\n"
    "3️⃣ Aquí en privado, activas con botones lo que quieras.\n\n"
    "Así configuras todo sin llenar el grupo de mensajes. 😎"
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _is_group_admin(context, group_id: int, user_id: int) -> bool:
    if config.is_admin(user_id):
        return True
    try:
        m = await context.bot.get_chat_member(group_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:  # noqa: BLE001
        return False


async def _group_title(group_id: int) -> str:
    sm = get_sessionmaker()
    async with sm() as s:
        g = await s.get(Group, group_id)
        return (g.title if g and g.title else None) or "tu grupo"


async def _user_groups(user_id: int) -> list[dict]:
    """Grupos que el usuario añadió (acceso rápido desde el panel)."""
    from sqlalchemy import select
    sm = get_sessionmaker()
    async with sm() as s:
        res = await s.execute(
            select(Group).where(Group.added_by == user_id, Group.is_active == True))  # noqa: E712
        return [{"id": g.id, "title": g.title or str(g.id)} for g in res.scalars()]


# --------------------------------------------------------------------------- #
# /start  (privado: onboarding + deep link; grupo: botón a privado)
# --------------------------------------------------------------------------- #
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await ensure_user(user.id, user.username, user.first_name)

    if is_group(update.effective_chat):
        await ensure_group(update.effective_chat.id, update.effective_chat.title, user.id)
        await _post_open_panel(update, context)
        return

    # Deep link: /start cfg_<group_id>
    args = context.args or []
    if args and args[0].startswith("cfg_"):
        try:
            gid = int(args[0][4:])
        except ValueError:
            gid = None
        if gid is not None:
            if not await _is_group_admin(context, gid, user.id):
                await update.effective_message.reply_text(
                    "🔒 Solo los administradores de ese grupo pueden configurarlo.")
                return
            text, kb = await _render_group(context, gid)
            await update.effective_message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            return

    await update.effective_message.reply_text(
        i18n.t("es", "pick_language"), parse_mode=ParseMode.MARKDOWN,
        reply_markup=i18n.lang_keyboard())


def _home_kb(lang: str = "es") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.t(lang, "btn_config"), callback_data="dash:groups")],
        [InlineKeyboardButton(i18n.t(lang, "btn_premium"), callback_data="dash:prem:0")],
        [
            InlineKeyboardButton(i18n.t(lang, "btn_what"), callback_data="dash:what"),
            InlineKeyboardButton(i18n.t(lang, "btn_lang"), callback_data="dash:lang:pick"),
        ],
    ])


async def _post_open_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """En el grupo: publica un único mensaje con el botón al panel privado."""
    bot_username = context.bot.username
    gid = update.effective_chat.id
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "⚙️ Abrir panel de configuración",
        url=f"https://t.me/{bot_username}?start=cfg_{gid}")]])
    await update.effective_message.reply_text(
        "🤖 *Bot_Gestor* está aquí.\n"
        "Para configurarme, pulsa el botón y te atiendo en privado "
        "(así no llenamos el grupo de mensajes).",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group(update.effective_chat):
        await update.effective_message.reply_text(
            "Usa /config dentro del grupo que quieres configurar.")
        return
    await ensure_group(update.effective_chat.id, update.effective_chat.title,
                       update.effective_user.id)
    await _post_open_panel(update, context)


# --------------------------------------------------------------------------- #
# Render del panel de un grupo
# --------------------------------------------------------------------------- #
async def _render_group(context, gid: int):
    cfg = await settings.get_all(gid)
    sub = await subscriptions.get_subscription(gid)
    premium = bool(sub and sub.get("active"))
    title = await _group_title(gid)
    plan = "💎 Premium" if premium else "🆓 Gratis"
    extra = f" · {sub['days_left']}d" if (premium and sub and sub.get("days_left") is not None) else ""

    # Resumen de qué está activo (estilo GroupHelp).
    activos = [lbl for key, lbl in settings.TOGGLES.items() if int(cfg.get(key, 0) or 0)]
    resumen = f"🟢 Activo: {len(activos)} funciones" if activos else "⚪ Nada activado aún"

    text = (
        f"⚙️ *Panel de configuración*\n"
        f"📍 {title}  ·  {plan}{extra}\n"
        "═══════════════\n"
        f"{resumen}\n\n"
        "Elige una categoría para configurarla 👇"
    )
    rows = [
        [InlineKeyboardButton("👋 Bienvenida y reglas", callback_data=f"dash:cat:{gid}:welcome")],
        [InlineKeyboardButton("🛡️ Moderación y filtros", callback_data=f"dash:cat:{gid}:mod")],
        [InlineKeyboardButton("⚠️ Advertencias", callback_data=f"dash:warn:{gid}")],
        [InlineKeyboardButton("🌙 Modo noche", callback_data=f"dash:night:{gid}")],
        [InlineKeyboardButton("🧠 IA, CAPTCHA y FAQ 💎", callback_data=f"dash:cat:{gid}:ai")],
        [InlineKeyboardButton("🎖️ Niveles y lista negra 💎", callback_data=f"dash:cat:{gid}:plus")],
        [InlineKeyboardButton("💎 Premium", callback_data=f"dash:prem:{gid}")],
    ]
    return text, InlineKeyboardMarkup(rows)


# Categorías: título, interruptores y acciones (botones que abren un flujo).
CATS = {
    "welcome": {
        "title": "👋 *Bienvenida y reglas*",
        "desc": "Saluda a los nuevos y muestra las normas.",
        "toggles": ["welcome_enabled", "goodbye_enabled"],
        "actions": [("✍️ Editar bienvenida", "set:welcome"),
                    ("📜 Editar reglas", "set:rules")],
    },
    "mod": {
        "title": "🛡️ *Moderación y filtros*",
        "desc": "Frena flood, enlaces y palabras prohibidas (los admins quedan exentos).",
        "toggles": ["antiflood_enabled", "antilinks_enabled", "antibadwords_enabled"],
        "actions": [],
    },
    "ai": {
        "title": "🧠 *IA, CAPTCHA y FAQ* 💎",
        "desc": "Verificación anti-bots, moderación con IA y auto-respuestas.",
        "toggles": ["captcha_enabled", "ai_moderation", "faq_enabled"],
        "actions": [],
    },
    "plus": {
        "title": "🎖️ *Niveles y lista negra* 💎",
        "desc": "Premia a los activos con niveles y banea globalmente a problemáticos.",
        "toggles": ["levels_enabled", "fedban_enabled"],
        "actions": [],
    },
}


async def _render_cat(query, context, gid: int, catkey: str):
    cat = CATS.get(catkey)
    if not cat:
        text, kb = await _render_group(context, gid)
        await _edit(query, text, kb)
        return
    cfg = await settings.get_all(gid)
    premium = await subscriptions.is_premium(gid)

    lines = [cat["title"], "═══════════════", f"_{cat['desc']}_", ""]
    if any(k in settings.PREMIUM_KEYS for k in cat["toggles"]) and not premium:
        lines.append("💎 _Estas funciones necesitan Premium._\n")

    rows = []
    for key in cat["toggles"]:
        mark = "✅" if int(cfg.get(key, 0) or 0) else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {settings.TOGGLES[key]}",
                                          callback_data=f"dash:tg:{gid}:{key}:{catkey}")])
    for label, act in cat["actions"]:
        rows.append([InlineKeyboardButton(label, callback_data=f"dash:{act}:{gid}")])
    rows.append([InlineKeyboardButton("‹ Atrás", callback_data=f"dash:cfg:{gid}")])
    await _edit(query, "\n".join(lines), InlineKeyboardMarkup(rows))


# --------------------------------------------------------------------------- #
# Router de callbacks del panel
# --------------------------------------------------------------------------- #
async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    action = parts[1]
    user = query.from_user

    if action == "nop":
        await query.answer()
        return

    if action == "home":
        await query.answer()
        lang = await get_lang(user.id)
        await _edit(query, i18n.t(lang, "intro"), _home_kb(lang))
        return

    if action == "what":
        await query.answer()
        lang = await get_lang(user.id)
        await _edit(query, i18n.t(lang, "what"), _back_home_kb(lang))
        return

    if action == "lang":
        choice = parts[2]
        if choice == "pick":
            await query.answer()
            await _edit(query, i18n.t(await get_lang(user.id), "pick_language"),
                        i18n.lang_keyboard())
            return
        # Guardar idioma elegido y mostrar el inicio en ese idioma.
        await set_lang(user.id, choice if choice in ("es", "en") else "es")
        lang = await get_lang(user.id)
        await query.answer(i18n.t(lang, "lang_set"))
        await _edit(query, i18n.t(lang, "intro"), _home_kb(lang))
        return

    if action == "groups":
        await query.answer()
        groups = await _user_groups(user.id)
        if not groups:
            await _edit(query,
                        "📭 *No veo grupos tuyos todavía.*\n\n"
                        "Añádeme a tu grupo, hazme *administrador* y escribe "
                        "/config ahí para abrir su panel.",
                        _back_home_kb())
            return
        rows = [[InlineKeyboardButton(f"📍 {g['title'][:30]}",
                                      callback_data=f"dash:cfg:{g['id']}")]
                for g in groups]
        rows.append([InlineKeyboardButton("‹ Volver", callback_data="dash:home")])
        await _edit(query, "⚙️ *Elige el grupo a configurar:*",
                    InlineKeyboardMarkup(rows))
        return

    if action == "prem":
        gid = int(parts[2])
        await query.answer()
        await _render_premium(query, context, gid)
        return

    # A partir de aquí todo requiere group_id y ser admin del grupo.
    gid = int(parts[2])
    if not await _is_group_admin(context, gid, user.id):
        await query.answer("Solo administradores del grupo.", show_alert=True)
        return

    if action == "cfg":
        await query.answer()
        text, kb = await _render_group(context, gid)
        await _edit(query, text, kb)

    elif action == "cat":
        await query.answer()
        await _render_cat(query, context, gid, parts[3])

    elif action == "tg":
        key = parts[3]
        catkey = parts[4] if len(parts) > 4 else None
        if key in settings.PREMIUM_KEYS and not await subscriptions.is_premium(gid):
            await query.answer("💎 Función Premium. Actívala en la sección Premium.",
                               show_alert=True)
            return
        await settings.toggle(gid, key)
        await query.answer("Actualizado ✅")
        # Volver a dibujar la vista de donde vino el interruptor.
        if catkey == "night":
            await _render_night(query, context, gid)
        elif catkey in CATS:
            await _render_cat(query, context, gid, catkey)
        else:
            text, kb = await _render_group(context, gid)
            await _edit(query, text, kb)

    elif action == "set":
        field = parts[3]
        context.user_data["dash_flow"] = {
            "field": field, "gid": gid,
            "msg_id": query.message.message_id, "chat_id": query.message.chat_id}
        await query.answer()
        if field == "welcome":
            prompt = ("✍️ *Escríbeme el mensaje de bienvenida.*\n\n"
                      "Puedes usar:\n`{nombre}` → nombre del nuevo miembro\n"
                      "`{grupo}` → nombre del grupo\n\n"
                      "_Ejemplo:_ ¡Hola {nombre}, bienvenido a {grupo}! 🎉")
        else:
            prompt = "📜 *Escríbeme las reglas del grupo.*\nEscríbelas tal cual quieres que se muestren."
        await _edit(query, prompt, _cancel_kb(gid))

    elif action == "warn":
        await query.answer()
        await _render_warn(query, context, gid)

    elif action == "num":
        key, val = parts[3], int(parts[4])
        await settings.set(gid, key, val)
        await query.answer("Guardado ✅")
        await _render_warn(query, context, gid)

    elif action == "wa":
        await settings.set(gid, "warn_action", parts[3])
        await query.answer("Guardado ✅")
        await _render_warn(query, context, gid)

    elif action == "night":
        await query.answer()
        await _render_night(query, context, gid)

    elif action == "nh":
        # Mostrar la rejilla de horas para 'start' o 'end'.
        which = parts[3]
        await query.answer()
        await _render_hours(query, gid, which)

    elif action == "nset":
        which, hour = parts[3], int(parts[4])
        key = "nightmode_start" if which == "start" else "nightmode_end"
        await settings.set(gid, key, hour)
        # Si configuran horas, activamos el modo noche automáticamente.
        if await subscriptions.is_premium(gid):
            await settings.set(gid, "nightmode_enabled", 1)
        await query.answer("Hora guardada ✅")
        await _render_night(query, context, gid)

    elif action == "redeem":
        context.user_data["dash_flow"] = {
            "field": "redeem", "gid": gid,
            "msg_id": query.message.message_id, "chat_id": query.message.chat_id}
        await query.answer()
        await _edit(query,
                    "🎟️ *Escríbeme el código de tu licencia.*\n"
                    "_Formato:_ `GEST-XXXX-XXXX-XXXX`",
                    _cancel_kb(gid))

    elif action == "buy":
        await query.answer()
        from bot.handlers.payments import send_invoice_for
        try:
            await send_invoice_for(context, query.message.chat_id, gid, user.id)
        except Exception as e:  # noqa: BLE001
            await query.message.reply_text(
                f"No pude generar el pago con Stars: {e}\n"
                "Puedes activar Premium con un código (botón 🎟️).")

    elif action == "cancel":
        context.user_data.pop("dash_flow", None)
        await query.answer("Cancelado")
        text, kb = await _render_group(context, gid)
        await _edit(query, text, kb)


# --------------------------------------------------------------------------- #
# Sub-paneles
# --------------------------------------------------------------------------- #
async def _render_warn(query, context, gid: int):
    cfg = await settings.get_all(gid)
    limit = int(cfg["warn_limit"])
    action = cfg["warn_action"]
    text = (f"⚠️ *Sistema de avisos*\n"
            f"═══════════════\n"
            f"Avisos antes de actuar: *{limit}*\n"
            f"Acción al llegar al límite: *{action}*\n\n"
            "Elige cuántos avisos y qué pasa al alcanzarlos:")
    num_row = [InlineKeyboardButton(("•" if n == limit else "") + str(n),
                                    callback_data=f"dash:num:{gid}:warn_limit:{n}")
               for n in (1, 2, 3, 4, 5)]
    act_row = [InlineKeyboardButton(("✅ " if a == action else "") + a,
                                    callback_data=f"dash:wa:{gid}:{a}")
               for a in ("mute", "kick", "ban")]
    kb = InlineKeyboardMarkup([
        num_row, act_row,
        [InlineKeyboardButton("‹ Volver", callback_data=f"dash:cfg:{gid}")],
    ])
    await _edit(query, text, kb)


async def _render_night(query, context, gid: int):
    cfg = await settings.get_all(gid)
    premium = await subscriptions.is_premium(gid)
    enabled = int(cfg.get("nightmode_enabled", 0) or 0)
    start_h, end_h = int(cfg["nightmode_start"]), int(cfg["nightmode_end"])
    estado = "✅ Activado" if enabled else "⬜ Desactivado"
    text = (
        "🌙 *Modo noche*\n"
        "═══════════════\n"
        f"Estado: *{estado}*\n"
        f"🌙 Cierra a las *{start_h:02d}:00*\n"
        f"☀️ Abre a las *{end_h:02d}:00*\n\n"
        "El grupo se cierra solo en ese horario y se reabre por la mañana, "
        "avisando a todos.\n"
    )
    if not premium:
        text += "\n💎 _Necesita Premium para activarse._"
    toggle_label = ("🌙 Desactivar modo noche" if enabled else "🌙 Activar modo noche")
    rows = [
        [InlineKeyboardButton(toggle_label, callback_data=f"dash:tg:{gid}:nightmode_enabled:night")],
        [
            InlineKeyboardButton(f"🕒 Cierre: {start_h:02d}:00", callback_data=f"dash:nh:{gid}:start"),
            InlineKeyboardButton(f"🕖 Apertura: {end_h:02d}:00", callback_data=f"dash:nh:{gid}:end"),
        ],
        [InlineKeyboardButton("‹ Volver", callback_data=f"dash:cfg:{gid}")],
    ]
    await _edit(query, text, InlineKeyboardMarkup(rows))


async def _render_hours(query, gid: int, which: str):
    titulo = "cierre 🌙" if which == "start" else "apertura ☀️"
    text = f"Elige la *hora de {titulo}* (formato 24h):"
    rows, row = [], []
    for h in range(24):
        row.append(InlineKeyboardButton(f"{h:02d}", callback_data=f"dash:nset:{gid}:{which}:{h}"))
        if len(row) == 6:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("‹ Volver", callback_data=f"dash:night:{gid}")])
    await _edit(query, text, InlineKeyboardMarkup(rows))


async def _render_premium(query, context, gid: int):
    from bot.handlers.premium import PREMIUM_INFO
    rows = []
    if gid:
        premium = await subscriptions.is_premium(gid)
        if premium:
            sub = await subscriptions.get_subscription(gid)
            text = (f"💎 *Premium activo*\n═══════════════\n"
                    f"Días restantes: *{sub['days_left']}*\n"
                    f"Disfruta todas las funciones. 🎉")
            rows.append([InlineKeyboardButton("‹ Volver", callback_data=f"dash:cfg:{gid}")])
        else:
            text = PREMIUM_INFO
            rows.append([InlineKeyboardButton("⭐ Pagar con Telegram Stars",
                                              callback_data=f"dash:buy:{gid}")])
            rows.append([InlineKeyboardButton("🎟️ Tengo un código",
                                              callback_data=f"dash:redeem:{gid}")])
            rows.append([InlineKeyboardButton("‹ Volver", callback_data=f"dash:cfg:{gid}")])
    else:
        text = PREMIUM_INFO
        rows.append([InlineKeyboardButton("‹ Volver", callback_data="dash:home")])
    await _edit(query, text, InlineKeyboardMarkup(rows))


# --------------------------------------------------------------------------- #
# Captura de texto de los flujos (bienvenida, reglas, código)
# --------------------------------------------------------------------------- #
async def on_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = context.user_data.get("dash_flow")
    if not flow:
        return
    text = (update.effective_message.text or "").strip()
    gid = flow["gid"]
    field = flow["field"]
    context.user_data.pop("dash_flow", None)

    note = ""
    if field == "welcome":
        await settings.set(gid, "welcome_text", text)
        await settings.set(gid, "welcome_enabled", 1)
        note = "✅ Bienvenida actualizada y activada."
    elif field == "rules":
        await settings.set(gid, "rules_text", text)
        note = "✅ Reglas guardadas."
    elif field == "redeem":
        try:
            result = await licenses.redeem(text, update.effective_user.id, gid)
            await audit(update.effective_user.id, "redeem", f"group={gid}")
            note = f"✅ ¡Premium activado por {result['days']} días! 💎"
        except licenses.RedeemError as e:
            note = str(e)

    # Quitar los botones del mensaje de "escríbeme..." para que no queden sueltos arriba.
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=flow["chat_id"], message_id=flow["msg_id"], reply_markup=None)
    except BadRequest:
        pass

    # Enviar un MENSAJE NUEVO (abajo) con la confirmación y el panel del grupo,
    # así el usuario lo ve sin tener que subir a buscar los botones.
    text_cfg, kb = await _render_group(context, gid)
    await update.effective_message.reply_text(
        f"{note}\n\n{text_cfg}", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


# --------------------------------------------------------------------------- #
# Teclados utilitarios
# --------------------------------------------------------------------------- #
def _back_home_kb(lang: str = "es") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        i18n.t(lang, "btn_back"), callback_data="dash:home")]])


def _cancel_kb(gid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Cancelar",
                                                       callback_data=f"dash:cancel:{gid}")]])


async def _edit(query, text: str, kb) -> None:
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                                      disable_web_page_preview=True)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            pass
