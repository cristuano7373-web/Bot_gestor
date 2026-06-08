"""Punto de entrada de Bot_Gestor.

Ejecuta el bot con:  python main.py
Requiere un archivo .env con BOT_TOKEN, ADMIN_IDS y DATABASE_URL.
"""
from telegram import Update

from logger import setup_logging
from bot.app import build_application


def main() -> None:
    log = setup_logging()
    app = build_application()
    log.info("Bot_Gestor despertando...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
