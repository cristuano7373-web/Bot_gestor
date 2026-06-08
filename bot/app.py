"""Construcción de la aplicación de Telegram y registro de handlers."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    MessageHandler, PreCheckoutQueryHandler, filters,
)

import config
from db.base import create_all, dispose
from bot.handlers import admin, core, dashboard, features, moderation, payments, premium

log = logging.getLogger("bot_gestor")


async def _post_init(app: Application) -> None:
    await create_all()
    log.info("Base de datos lista (%s)", config.DATABASE_URL.split("://")[0])

    # Reprogramar mensajes programados que sobrevivieron a un reinicio.
    await features.restore_schedules(app)

    # Jobs periódicos.
    if app.job_queue:
        from services import subscriptions
        async def _expire(ctx):
            n = await subscriptions.expire_due()
            if n:
                log.info("Suscripciones expiradas: %d", n)
        app.job_queue.run_repeating(_expire, interval=3600, first=60)
        # Modo nocturno: revisar cada 5 minutos.
        app.job_queue.run_repeating(features.nightmode_tick, interval=300, first=30)

    await app.bot.set_my_commands([
        ("start", "Iniciar / abrir el panel"),
        ("config", "Configurar el grupo (admins)"),
        ("help", "Lista de comandos"),
        ("stats", "Estadísticas del grupo"),
        ("premium", "Ver y activar Premium"),
        ("premium_status", "Estado de tu suscripción"),
        ("redeem", "Canjear una licencia"),
        ("reglas", "Ver reglas"),
    ])


async def _post_shutdown(app: Application) -> None:
    await dispose()
    log.info("Recursos liberados.")


async def _on_error(update: object, context) -> None:
    log.error("Excepción en handler:", exc_info=context.error)


def build_application() -> Application:
    config.validate()
    app = (ApplicationBuilder().token(config.BOT_TOKEN)
           .post_init(_post_init).post_shutdown(_post_shutdown).build())

    # --- Núcleo ---
    app.add_handler(CommandHandler("start", dashboard.cmd_start))
    app.add_handler(CommandHandler(["help", "ayuda"], core.cmd_help))
    app.add_handler(CommandHandler(["config", "panel", "configurar"], dashboard.cmd_config))
    app.add_handler(CommandHandler(["reglas", "rules"], core.cmd_rules))
    app.add_handler(CommandHandler(["setreglas", "setrules"], core.cmd_setrules))
    app.add_handler(CommandHandler(["setbienvenida", "setwelcome"], core.cmd_setwelcome))
    app.add_handler(CommandHandler(["stats", "estadisticas"], core.cmd_stats))
    app.add_handler(CommandHandler(["reporte", "report"], core.cmd_report))
    app.add_handler(CommandHandler(["nivel", "level"], core.cmd_level))

    # --- Moderación ---
    app.add_handler(CommandHandler("ban", moderation.cmd_ban))
    app.add_handler(CommandHandler(["kick", "expulsar"], moderation.cmd_kick))
    app.add_handler(CommandHandler(["mute", "silenciar"], moderation.cmd_mute))
    app.add_handler(CommandHandler(["unmute", "reactivar"], moderation.cmd_unmute))
    app.add_handler(CommandHandler(["warn", "advertir"], moderation.cmd_warn))

    # --- Premium ---
    app.add_handler(CommandHandler("premium", premium.cmd_premium))
    app.add_handler(CommandHandler("premium_info", premium.cmd_premium_info))
    app.add_handler(CommandHandler("premium_status", premium.cmd_premium_status))
    app.add_handler(CommandHandler("subscription", premium.cmd_subscription))
    app.add_handler(CommandHandler("redeem", premium.cmd_redeem))

    # --- Admin ---
    app.add_handler(CommandHandler("adminpanel", admin.cmd_adminpanel))
    app.add_handler(CommandHandler("createlicense", admin.cmd_createlicense))
    app.add_handler(CommandHandler("revokelicense", admin.cmd_revokelicense))
    app.add_handler(CommandHandler("premiumusers", admin.cmd_premiumusers))
    app.add_handler(CommandHandler("statsglobal", admin.cmd_statsglobal))
    app.add_handler(CommandHandler(["premiumgroups", "grupospremium"], admin.cmd_premiumgroups))
    app.add_handler(CommandHandler(["delpremium", "quitarpremium"], admin.cmd_delpremium))
    app.add_handler(CommandHandler("balance", admin.cmd_balance))
    app.add_handler(CommandHandler("payments", admin.cmd_payments))
    app.add_handler(CommandHandler("refund", admin.cmd_refund))
    app.add_handler(CommandHandler("refundlast", admin.cmd_refundlast))

    # --- Pagos (Telegram Stars) ---
    app.add_handler(PreCheckoutQueryHandler(payments.on_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payments.on_successful_payment))

    # --- Funciones Premium avanzadas ---
    app.add_handler(CommandHandler("faq", features.cmd_faq_add))
    app.add_handler(CommandHandler(["faqdel", "delfaq"], features.cmd_faq_del))
    app.add_handler(CommandHandler(["faqs", "faqlist"], features.cmd_faq_list))
    app.add_handler(CommandHandler(["programar", "schedule"], features.cmd_schedule))
    app.add_handler(CommandHandler(["programados", "schedules"], features.cmd_schedules))
    app.add_handler(CommandHandler(["cancelprog", "cancelschedule"], features.cmd_cancel_schedule))
    app.add_handler(CommandHandler(["nochehoras", "setnight"], features.cmd_setnight))
    app.add_handler(CommandHandler("fban", features.cmd_fban))
    app.add_handler(CommandHandler("unfban", features.cmd_unfban))
    app.add_handler(CommandHandler(["fbanlist", "fbans"], features.cmd_fbanlist))

    # --- Callbacks ---
    app.add_handler(CallbackQueryHandler(dashboard.cb, pattern=r"^dash:"))
    app.add_handler(CallbackQueryHandler(core.cb_captcha, pattern=r"^captcha:"))
    app.add_handler(CallbackQueryHandler(premium.cb_premium, pattern=r"^(buy_premium|have_code)$"))

    # --- Eventos de miembros ---
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, core.on_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, core.on_left_member))

    # --- Texto en PRIVADO: flujos guiados del panel (bienvenida, reglas, código) ---
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        dashboard.on_private_text))

    # --- Automod: cualquier mensaje de grupo (último) ---
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
        moderation.automod))

    app.add_error_handler(_on_error)
    return app
