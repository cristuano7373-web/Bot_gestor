"""Panel y comandos de administrador del producto.

/adminpanel /createlicense /revokelicense /premiumusers /statsglobal
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from security.permissions import admin_only
from services import licenses, stats, subscriptions
from services import payments as payments_svc
from services.entities import audit


@admin_only
async def cmd_adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "👑 *PANEL DEL DUEÑO*\n"
        "═══════════════\n\n"
        "🎟️ *Licencias (claves)*\n"
        "`/createlicense <cant> <días>` — generar claves\n"
        "   _ej:_ `/createlicense 5 30`\n"
        "`/revokelicense <código>` — anular una clave sin canjear\n"
        "`/premiumusers` — ver claves recientes y su estado\n\n"
        "💎 *Premium de grupos*\n"
        "`/premiumgroups` — listar grupos Premium (con su ID)\n"
        "`/delpremium <group_id>` — quitar Premium a un grupo\n\n"
        "⭐ *Pagos (Stars)*\n"
        "`/payments` — ver pagos recibidos (con su ID de cargo)\n"
        "`/refund <charge_id>` — reembolsar un pago concreto\n"
        "`/refundlast` — reembolsar el último pago\n"
        "`/balance` — saldo de Stars del bot\n\n"
        "📊 *Métricas*\n"
        "`/statsglobal` — grupos, Premium e ingresos totales\n\n"
        "═══════════════\n"
        "💡 *Flujo típico para vender:*\n"
        "1) `/createlicense 1 30` → copias la clave\n"
        "2) Se la das al cliente que te pagó\n"
        "3) Él la canjea con `/redeem CLAVE` en su grupo\n"
        "4) Si hace falta: `/premiumgroups` y `/delpremium <id>`",
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
async def cmd_premiumgroups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    groups = await subscriptions.list_premium_groups()
    if not groups:
        await update.effective_message.reply_text("No hay grupos Premium activos.")
        return
    lines = ["💎 *Grupos Premium activos*", "━━━━━━━━━━━━━━━"]
    for g in groups:
        lines.append(f"`{g['group_id']}` · {g['days_left']} días · {g['source'] or '—'}")
    lines.append("\nQuitar Premium: `/delpremium ID`")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args or not args[0].lstrip("-").isdigit():
        await update.effective_message.reply_text(
            "Uso: /delpremium <group_id>\n(Ve los IDs con /premiumgroups)")
        return
    gid = int(args[0])
    ok = await subscriptions.deactivate_group(gid)
    if ok:
        await audit(update.effective_user.id, "delpremium", str(gid))
        await update.effective_message.reply_text(
            f"✅ Premium retirado al grupo `{gid}`. Ahora es plan Gratis.",
            parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(
            "Ese grupo no tenía suscripción registrada.")


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
    lines.append("\nReembolsar: `/refund ID`  ·  o /refundlast")
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
