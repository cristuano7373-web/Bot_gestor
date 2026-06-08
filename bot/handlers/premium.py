"""Comandos Premium del usuario: /premium /premium_info /premium_status
/redeem /subscription."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from bot.common import is_group
from security.ratelimit import rate_limiter
from services import licenses, subscriptions
from services.entities import audit

PREMIUM_INFO = (
    "💎 *Bot_Gestor Premium*\n"
    "━━━━━━━━━━━━━━━\n"
    "Desbloquea lo mejor para tu grupo:\n\n"
    "🧠 Moderación con IA (spam, insultos, estafas)\n"
    "📊 Reportes semanales/mensuales + export CSV/Excel\n"
    "📈 Análisis de crecimiento\n"
    "⏰ Mensajes y encuestas programadas\n"
    "🤖 Respuestas automáticas inteligentes\n"
    "🎖️ Sistema de niveles y rangos con recompensas\n"
    "🖥️ Dashboard web en tiempo real\n\n"
    f"💰 *{config.PREMIUM_STARS_PRICE}⭐ / {config.PREMIUM_DAYS} días*"
)


HOW_TO_ACTIVATE = (
    "\n\n*¿Cómo activarlo?* (siempre dentro del grupo 👥)\n"
    "🎟️ Con licencia: `/redeem TU-CODIGO`\n"
    "⭐ Con Telegram Stars: escribe `/premium` en el grupo y pulsa pagar.\n"
    "_El Premium se activa por grupo, no por tu cuenta._"
)


def _buy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ Pagar con Telegram Stars",
                              callback_data="buy_premium")],
        [InlineKeyboardButton("🎟️ Tengo un código", callback_data="have_code")],
    ])


async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # En grupo: ofrecer botones de pago/código. En privado: explicar el flujo.
    if is_group(update.effective_chat):
        await update.effective_message.reply_text(
            PREMIUM_INFO, parse_mode=ParseMode.MARKDOWN, reply_markup=_buy_keyboard())
    else:
        await update.effective_message.reply_text(
            PREMIUM_INFO + HOW_TO_ACTIVATE, parse_mode=ParseMode.MARKDOWN)


async def cmd_premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        PREMIUM_INFO + HOW_TO_ACTIVATE, parse_mode=ParseMode.MARKDOWN)


async def cmd_premium_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _status(update)


async def cmd_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _status(update)


async def _status(update: Update) -> None:
    chat = update.effective_chat
    if not is_group(chat):
        await update.effective_message.reply_text(
            "ℹ️ El estado Premium es por *grupo*. Usa este comando dentro del grupo.",
            parse_mode=ParseMode.MARKDOWN)
        return
    sub = await subscriptions.get_subscription(chat.id)
    if not sub or not sub["active"]:
        await update.effective_message.reply_text(
            "🆓 Este grupo usa el *plan Gratis*.\nActívalo con /premium.",
            parse_mode=ParseMode.MARKDOWN)
        return
    src = {"license": "licencia", "stars": "Telegram Stars"}.get(sub["source"], sub["source"])
    await update.effective_message.reply_text(
        f"💎 *Premium activo*\n"
        f"⏳ Días restantes: *{sub['days_left']}*\n"
        f"📅 Expira: {sub['expires_at'][:10]}\n"
        f"🔗 Origen: {src}\n"
        f"🔁 Renovación automática: {'sí' if sub['auto_renew'] else 'no'}",
        parse_mode=ParseMode.MARKDOWN)


async def cmd_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not is_group(chat):
        await update.effective_message.reply_text(
            "ℹ️ Usa /redeem *dentro del grupo* que quieres hacer Premium.",
            parse_mode=ParseMode.MARKDOWN)
        return

    # Rate limit anti fuerza bruta de códigos.
    if not rate_limiter.allow(user.id, "redeem", limit=5, window=60):
        wait = rate_limiter.retry_after(user.id, "redeem", 60)
        await update.effective_message.reply_text(
            f"⏳ Demasiados intentos. Prueba de nuevo en {wait}s.")
        return

    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Uso: /redeem CODIGO")
        return
    try:
        result = await licenses.redeem(args[0], user.id, chat.id)
    except licenses.RedeemError as e:
        await update.effective_message.reply_text(str(e))
        return
    await audit(user.id, "redeem", f"group={chat.id} code={args[0]}")
    await update.effective_message.reply_text(
        f"✅ *¡Premium activado!*\nEste grupo es Premium por *{result['days']} días*. 💎",
        parse_mode=ParseMode.MARKDOWN)


# --------- Callbacks de los botones de /premium ---------
async def cb_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == "have_code":
        await query.answer()
        await query.message.reply_text("Escribe: /redeem TU-CODIGO (dentro del grupo).")
        return
    if query.data == "buy_premium":
        await query.answer()
        from bot.handlers.payments import send_invoice
        await send_invoice(update, context)
