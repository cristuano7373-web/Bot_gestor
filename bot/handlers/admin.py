"""Panel y comandos de administrador del producto.

/adminpanel /createlicense /revokelicense /premiumusers /statsglobal
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from security.permissions import admin_only
from services import licenses, stats
from services import payments as payments_svc
from services.entities import audit


@admin_only
async def cmd_adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🛠️ *Panel de administrador*\n"
        "━━━━━━━━━━━━━━━\n"
        "🎟️ /createlicense <cantidad> <días> — generar licencias\n"
        "   _ej:_ `/createlicense 5 30`\n"
        "🚫 /revokelicense <código> — revocar una licencia\n"
        "📜 /premiumusers — licencias recientes\n"
        "📊 /statsglobal — métricas globales del bot\n",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_createlicense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    count = int(args[0]) if args and args[0].isdigit() else 1
    days = int(args[1]) if len(args) > 1 and args[1].isdigit() else config.PREMIUM_DAYS
    count = max(1, min(50, count))
    codes = await licenses.create_licenses(count, days, update.effective_user.id)
    await audit(update.effective_user.id, "createlicense", f"count={count} days={days}")
    listado = "\n".join(f"`{c}`" for c in codes)
    await update.effective_message.reply_text(
        f"🎟️ *{count} licencia(s) de {days} días generadas:*\n{listado}\n\n"
        "Compártelas. Se canjean con /redeem CODIGO dentro de un grupo.",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_revokelicense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Uso: /revokelicense CODIGO")
        return
    ok = await licenses.revoke(args[0])
    if ok:
        await audit(update.effective_user.id, "revokelicense", args[0])
        await update.effective_message.reply_text("🚫 Licencia revocada.")
    else:
        await update.effective_message.reply_text(
            "No se pudo revocar (no existe o ya fue canjeada).")


@admin_only
async def cmd_premiumusers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = await licenses.list_recent(20)
    if not rows:
        await update.effective_message.reply_text("No hay licencias todavía.")
        return
    lines = ["📜 *Licencias recientes*", "━━━━━━━━━━━━━━━"]
    for r in rows:
        estado = "✅ canjeada" if r["redeemed"] else ("🚫 revocada" if r["revoked"] else "🟢 libre")
        lines.append(f"`{r['code']}` · {r['days']}d · {estado}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_statsglobal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    g = await stats.global_stats()
    await update.effective_message.reply_text(
        "📊 *Métricas globales*\n"
        "━━━━━━━━━━━━━━━\n"
        f"👥 Grupos con actividad: {g['groups_with_activity']}\n"
        f"💎 Grupos Premium: {g['premium_groups']}\n"
        f"⭐ Ingresos en Stars: {g['stars_revenue']}\n",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Saldo de Stars acumulado por el bot."""
    try:
        bal = await context.bot.get_my_star_balance()
        amount = getattr(bal, "amount", bal)
        await update.effective_message.reply_text(f"⭐ Saldo del bot: *{amount}* Stars.",
                                                   parse_mode=ParseMode.MARKDOWN)
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(
            f"No pude consultar el saldo: {e}\n"
            "Requiere una versión reciente de la API; revisa también @BotFather.")


@admin_only
async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = await payments_svc.list_paid(10)
    if not rows:
        await update.effective_message.reply_text("No hay pagos registrados.")
        return
    lines = ["⭐ *Pagos recientes*", "━━━━━━━━━━━━━━━"]
    for r in rows:
        lines.append(f"#{r['id']} · {r['amount']}⭐ · {r['status']}\n  `{r['charge_id']}`")
    lines.append("\nReembolsar: /refund <charge_id>  ·  o /refundlast")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def _do_refund(update, context, payment: dict) -> None:
    """Reembolsa un pago en Stars al usuario que pagó."""
    try:
        await context.bot.refund_star_payment(
            user_id=payment["user_id"],
            telegram_payment_charge_id=payment["charge_id"],
        )
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ No pude reembolsar: {e}")
        return
    await payments_svc.mark_refunded(payment["charge_id"])
    await audit(update.effective_user.id, "refund", payment["charge_id"])
    await update.effective_message.reply_text(
        f"✅ Reembolsadas *{payment['amount']}⭐* a la cuenta que pagó "
        f"(user `{payment['user_id']}`).", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args:
        await update.effective_message.reply_text(
            "Uso: /refund <charge_id>\n(Ver IDs con /payments, o usa /refundlast)")
        return
    payment = await payments_svc.get_by_charge(args[0])
    if not payment:
        await update.effective_message.reply_text("No encuentro ese pago.")
        return
    if payment["status"] == "refunded":
        await update.effective_message.reply_text("Ese pago ya fue reembolsado.")
        return
    await _do_refund(update, context, payment)


@admin_only
async def cmd_refundlast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = await payments_svc.get_last_paid()
    if not payment:
        await update.effective_message.reply_text("No hay pagos pendientes de reembolsar.")
        return
    await _do_refund(update, context, payment)
