"""Textos en varios idiomas (español / inglés).

Uso: t(lang, "clave"). Si falta la traducción, cae a español.
De momento se traducen las pantallas de inicio y el menú principal (lo que el
usuario ve "al ejecutar el bot"). Los paneles internos se pueden traducir
incrementalmente añadiendo más claves aquí.
"""
from __future__ import annotations

T: dict[str, dict[str, str]] = {
    "es": {
        "pick_language": (
            "🌐 *Elige tu idioma* / *Choose your language*\n"
            "═══════════════\n"
            "Selecciona el idioma del bot 👇"
        ),
        "intro": (
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
        ),
        "what": (
            "❓ *¿Qué es Bot_Gestor?*\n"
            "═══════════════\n"
            "Es un bot para *administrar grupos de Telegram* de forma automática.\n\n"
            "*Cómo se usa en 3 pasos:*\n"
            "1️⃣ Me añades a tu grupo y me haces *administrador*.\n"
            "2️⃣ Escribes /config en el grupo y pulsas *Abrir panel*.\n"
            "3️⃣ Aquí en privado, activas con botones lo que quieras.\n\n"
            "Así configuras todo sin llenar el grupo de mensajes. 😎"
        ),
        "btn_config": "⚙️ Configurar un grupo",
        "btn_premium": "💎 Premium",
        "btn_what": "❓ ¿Qué es esto?",
        "btn_lang": "🌐 Idioma",
        "btn_back": "‹ Volver",
        "lang_set": "✅ Idioma cambiado a Español 🇪🇸",
    },
    "en": {
        "pick_language": (
            "🌐 *Choose your language* / *Elige tu idioma*\n"
            "═══════════════\n"
            "Select the bot language 👇"
        ),
        "intro": (
            "🤖 *Bot_Gestor*\n"
            "_The assistant that manages your group for you._\n"
            "═══════════════\n\n"
            "I take care of:\n"
            "🛡️ Stopping spam, flood, links and bots\n"
            "👋 Welcoming new members\n"
            "📊 Showing you group statistics\n"
            "🎖️ Rewarding the most active with levels\n"
            "⏰ Sending scheduled messages\n"
            "💎 And much more with Premium\n\n"
            "👇 Start by configuring a group."
        ),
        "what": (
            "❓ *What is Bot_Gestor?*\n"
            "═══════════════\n"
            "It's a bot to *manage Telegram groups* automatically.\n\n"
            "*How to use it in 3 steps:*\n"
            "1️⃣ Add me to your group and make me an *administrator*.\n"
            "2️⃣ Type /config in the group and tap *Open panel*.\n"
            "3️⃣ Here in private, enable whatever you want with buttons.\n\n"
            "That way you set everything up without flooding the group. 😎"
        ),
        "btn_config": "⚙️ Configure a group",
        "btn_premium": "💎 Premium",
        "btn_what": "❓ What is this?",
        "btn_lang": "🌐 Language",
        "btn_back": "‹ Back",
        "lang_set": "✅ Language set to English 🇬🇧",
    },
}


def t(lang: str, key: str) -> str:
    lang = lang if lang in T else "es"
    return T[lang].get(key) or T["es"].get(key, key)


def lang_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇪🇸 Español", callback_data="dash:lang:es"),
            InlineKeyboardButton("🇬🇧 English", callback_data="dash:lang:en"),
        ],
    ])
