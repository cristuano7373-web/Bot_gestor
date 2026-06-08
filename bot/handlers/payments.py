"""Pagos con Telegram Stars (XTR) — Método B.

Flujo:
  1. send_invoice: envía una factura en Stars (currency 'XTR', provider_token vacío).
  2. pre_checkout: Telegram pregunta antes de cobrar -> respondemos OK.
  3. on_successful_payment: tras el cobro, activamos Premium y guardamos el pago.
"""
from __future__ import annotations

import logging

from telegram import LabeledPrice, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from bot.common import is_group
from services import session_scope, subscriptions
from services.entities import audit
from db.models import Payment

log = logging.getLogger("bot_gestor")

PAYLOAD_PREFIX = "premium"


async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if not is_group(chat):
        target = update.effective_message or (update.callback_query and update.callback_query.message)
        if target:
            await target.reply_text(
                "ℹ️ Compra el Premium *dentro del grupo* que quieres mejorar.",
                parse_mode=ParseMode.MARKDOWN)
        return
    await send_invoice_for(context, chat.id, chat.id, user.id)


async def send_invoice_for(context: ContextTypes.DEFAULT_TYPE, send_chat_id: int,
                           group_id: int, user_id: int) -> None:
    """Envía la factura de Stars a `send_chat_id` para activar Premium en `group_id`.

    Permite cobrar desde el chat privado (panel) o desde el propio grupo.
    """
    payload = f"{PAYLOAD_PREFIX}:{group_id}:{user_id}"
    await context.bot.send_invoice(
        chat_id=send_chat_id,
        title="Bot_Gestor Premium",
        description=f"Premium para tu grupo durante {config.PREMIUM_DAYS} días. "
                    "Moderación IA, reportes, niveles, dashboard y más.",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium", amount=config.PREMIUM_STARS_PRICE)],
    )


async def on_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    # Validar el payload antes de aprobar el cobro.
    if q.invoice_payload.startswith(PAYLOAD_PREFIX + ":"):
        await q.answer(ok=True)
    else:
        await q.answer(ok=False, error_message="Pago no válido. Inténtalo de nuevo.")


async def on_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    sp = msg.successful_payment
    user = update.effective_user
    try:
        _, group_id_s, _ = sp.invoice_payload.split(":")
        group_id = int(group_id_s)
    except Exception:  # noqa: BLE001
        group_id = update.effective_chat.id

    # Guardar el pago (idempotente por telegram_charge_id único).
    charge_id = sp.telegram_payment_charge_id
    async with session_scope() as s:
        from sqlalchemy import select
        exists = await s.execute(
            select(Payment).where(Payment.telegram_charge_id == charge_id))
        if exists.scalar_one_or_none() is None:
            s.add(Payment(
                user_id=user.id, group_id=group_id, amount=sp.total_amount,
                currency=sp.currency, telegram_charge_id=charge_id,
                payload=sp.invoice_payload, status="paid",
            ))

    await subscriptions.activate_premium(
        group_id, days=config.PREMIUM_DAYS, source="stars",
        activated_by=user.id, auto_renew=True,
    )
    await audit(user.id, "payment", f"group={group_id} stars={sp.total_amount}")
    await msg.reply_text(
        f"✅ *¡Pago recibido! Premium activado* por {config.PREMIUM_DAYS} días. 💎\n"
        "Gracias por tu apoyo ⭐",
        parse_mode=ParseMode.MARKDOWN)


async def cmd_refund_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram permite reembolsos de Stars; aquí solo informamos."""
    await update.effective_message.reply_text(
        "Los pagos con Stars se gestionan vía Telegram. Para reembolsos, "
        "contacta al soporte del bot.")
