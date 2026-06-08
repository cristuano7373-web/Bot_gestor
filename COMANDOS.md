# 📋 Comandos de Bot_Gestor

Lista completa de comandos y qué hace cada uno.

**Leyenda:**
- 👤 = cualquier usuario · 🛡️ = admin del grupo · 👑 = admin del bot (tu ID en `ADMIN_IDS`)
- 💎 = requiere Premium activo en el grupo

---

## 🏁 General

| Comando | Quién | Función |
|---|---|---|
| `/start` | 👤 | Inicia el bot. En privado muestra el menú; en grupo confirma que está activo. |
| `/help` · `/ayuda` | 👤 | Muestra la guía de comandos por categorías. |
| `/panel` | 🛡️ | Panel de configuración con botones: activa/desactiva cada función. |

---

## 🛡️ Moderación

| Comando | Quién | Función |
|---|---|---|
| `/ban` | 🛡️ | Banea a un usuario (responde a su mensaje o `/ban ID`). |
| `/unban` | 🛡️ | Quita el baneo a un usuario. |
| `/kick` · `/expulsar` | 🛡️ | Expulsa al usuario (puede volver con invitación). |
| `/mute [min]` · `/silenciar` | 🛡️ | Silencia al usuario. Opcional: minutos (`/mute 30`). |
| `/unmute` · `/reactivar` | 🛡️ | Devuelve la voz a un usuario silenciado. |
| `/warn [motivo]` · `/advertir` | 🛡️ | Da una advertencia. Al llegar al límite aplica la acción configurada (mute/kick/ban). |

**Filtros automáticos (se activan en `/panel`):** antiflood, anti-enlaces,
anti-palabras y antispam. Los administradores quedan exentos.

---

## 📝 Configuración del grupo

| Comando | Quién | Función |
|---|---|---|
| `/reglas` · `/rules` | 👤 | Muestra las reglas del grupo. |
| `/setreglas <texto>` | 🛡️ | Define las reglas del grupo. |
| `/setbienvenida <texto>` | 🛡️ | Define el mensaje de bienvenida. Variables: `{nombre}`, `{grupo}`. |

---

## 📊 Estadísticas

| Comando | Quién | Función |
|---|---|---|
| `/stats` · `/estadisticas` | 👤 | Resumen de 7 días: mensajes, usuarios activos, nuevos miembros, ranking y gráfico. |

---

## 💎 Funciones Premium

| Comando | Quién | Función |
|---|---|---|
| `/premium` | 👤 | Muestra el plan Premium y cómo activarlo. |
| `/premium_info` | 👤 | Detalle de lo que incluye Premium. |
| `/premium_status` · `/subscription` | 👤 | Estado de la suscripción del grupo (días restantes). |
| `/redeem <código>` | 👤 | Canjea una licencia para activar Premium en el grupo. |
| `/reporte [semanal\|mensual]` | 💎 🛡️ | Genera un reporte de actividad y lo exporta en CSV. |
| `/nivel` · `/level` | 💎 👤 | Muestra tu nivel y XP en el grupo. |
| `/faq palabra \| respuesta` | 💎 🛡️ | Crea una auto-respuesta por palabra clave. |
| `/faqs` · `/faqlist` | 👤 | Lista las auto-respuestas configuradas. |
| `/faqdel <palabra>` | 🛡️ | Elimina una auto-respuesta. |
| `/programar CUANDO \| TEXTO` | 💎 🛡️ | Mensaje programado. Ej: `18:30` (una vez) o `6h`/`1d` (recurrente). |
| `/programados` · `/schedules` | 🛡️ | Lista los mensajes programados. |
| `/cancelprog <id>` | 🛡️ | Cancela un mensaje programado. |
| `/nochehoras <inicio> <fin>` | 💎 🛡️ | Configura el modo nocturno. Ej: `/nochehoras 23 7`. |
| `/fban [motivo]` | 💎 🛡️ | Añade a un usuario a tu lista negra global y lo banea en todos tus grupos. |
| `/unfban` | 🛡️ | Quita a un usuario de la lista negra global. |
| `/fbanlist` · `/fbans` | 🛡️ | Muestra tu lista negra global. |

**Funciones automáticas Premium (se activan en `/panel`):**
- 🤖 **CAPTCHA anti-bots**: el nuevo miembro debe verificarse o es expulsado.
- 🧠 **Moderación IA**: detecta spam, insultos y estafas.
- 💬 **Auto-respuestas**: responde solo a las palabras clave del FAQ.
- 🎖️ **Niveles**: gana XP por participar y sube de nivel.
- 🌙 **Modo nocturno**: cierra el grupo en el horario configurado.
- 🛡️ **Lista negra global**: aplica los baneos de federación al entrar.

---

## 👑 Administración del bot (solo tú)

| Comando | Función |
|---|---|
| `/adminpanel` | Panel con los comandos de administrador. |
| `/createlicense <cantidad> <días>` | Genera licencias. Ej: `/createlicense 5 30`. |
| `/revokelicense <código>` | Revoca una licencia no canjeada. |
| `/premiumusers` | Lista las licencias recientes y su estado. |
| `/statsglobal` | Métricas globales: grupos, Premium e ingresos en Stars. |
| `/payments` | Lista los pagos recibidos (con su charge_id). |
| `/refund <charge_id>` | Reembolsa un pago en Stars al usuario que pagó. |
| `/refundlast` | Reembolsa el último pago registrado. |
| `/balance` | Muestra el saldo de Stars del bot (si la API lo permite). |

---

## 💳 Cómo se activa el Premium

1. **Con licencia:** generas un código con `/createlicense` y el usuario lo canjea
   con `/redeem CODIGO` **dentro de su grupo**.
2. **Con Telegram Stars:** en el grupo, `/premium` → botón ⭐ → pago dentro de
   Telegram → se activa solo.

> El Premium se activa **por grupo**, no por cuenta. El bot debe ser
> **administrador** del grupo para moderar, banear y cerrar (modo nocturno).
