# 🤖 Bot_Gestor — Administrador de grupos de Telegram (SaaS)

Bot de Telegram **comercializable** para administración avanzada de grupos, con
plan **Gratis** y plan **Premium** (licencias canjeables + pago con Telegram
Stars). Arquitectura modular, base de datos PostgreSQL, seguridad y código
limpio y documentado.

> Estado de la entrega: el **núcleo de producto está implementado y probado**
> (BD completa, licencias, Premium, Telegram Stars, moderación, estadísticas,
> seguridad, niveles). El **Dashboard web** y la **IA con modelo externo** se
> entregan como módulos con base funcional y puntos de extensión claros
> (ver "Hoja de ruta").

## 🧱 Arquitectura

```
bot_gestor/
├─ main.py               # Entry point (polling)
├─ config.py            # Configuración desde .env
├─ logger.py            # Logging a consola + archivo
├─ db/
│  ├─ base.py           # Engine/sesiones async (PostgreSQL o SQLite)
│  └─ models.py         # Todas las tablas (SQLAlchemy 2.0)
├─ services/            # Lógica de negocio (sin Telegram, testeable)
│  ├─ entities.py       # usuarios, grupos, auditoría
│  ├─ licenses.py       # generar / canjear / revocar licencias
│  ├─ subscriptions.py  # estado Premium (activar / extender / expirar)
│  ├─ settings.py       # configuración por grupo
│  └─ stats.py          # actividad, rankings, reportes
├─ security/
│  ├─ crypto.py         # cifrado Fernet de datos sensibles
│  ├─ ratelimit.py      # rate limiting (anti-abuso)
│  └─ permissions.py    # decoradores admin / admin de grupo
├─ moderation/
│  ├─ filters.py        # antiflood, anti-enlaces, anti-palabras, antispam
│  └─ ai.py             # moderación IA (heurística pluggable)
├─ bot/
│  ├─ common.py         # helpers + gate Premium
│  ├─ app.py            # construcción de la app y handlers
│  └─ handlers/         # core, moderation, premium, payments, admin
└─ smoke_test.py        # pruebas del núcleo sobre SQLite
```

**Decisiones técnicas**
- `python-telegram-bot` v21 (async) — soporta pagos **Telegram Stars** y `JobQueue`.
- **SQLAlchemy 2.0 async**: mismo código para PostgreSQL (prod, `asyncpg`) y
  SQLite (dev/tests). Solo cambia `DATABASE_URL`.
- Lógica de negocio separada de Telegram → unitariamente testeable.

## 🗄️ Base de datos (tablas)

| Tabla | Para qué |
|---|---|
| `users` | Usuarios conocidos por el bot |
| `groups` | Grupos donde está el bot |
| `group_settings` | Configuración por grupo (clave/valor) |
| `licenses` | Licencias canjeables (Método A), código único |
| `subscriptions` | Estado Premium por grupo (licencia o Stars) |
| `payments` | Historial de pagos en Stars |
| `message_stats` | Actividad diaria por grupo/usuario |
| `warns` | Advertencias de moderación |
| `user_levels` | XP y nivel por usuario (Premium) |
| `audit_logs` | Registro de acciones sensibles |

## ✨ Funciones

**Gratis**: moderación (antiflood, anti-enlaces, anti-palabras, antispam, mute,
kick, ban, warns con acción automática), bienvenidas/despedidas, reglas,
estadísticas (activos, mensajes, nuevos, ranking, gráfico), panel por botones.

**Premium 💎**:
- 🤖 **CAPTCHA anti-bots**: el nuevo miembro debe pulsar "Soy humano" en X
  segundos o es expulsado (mata el spam de cuentas falsas).
- 🧠 **Moderación con IA**: detecta spam, insultos y estafas.
- 💬 **Auto-respuestas / FAQ**: el bot responde solo a palabras clave.
- ⏰ **Mensajes programados**: únicos (`18:30`) o recurrentes (`6h`, `1d`).
- 🌙 **Modo nocturno**: cierra el grupo automáticamente en un horario.
- 🛡️ **Lista negra global (federación)**: banear a alguien en todos tus grupos.
- 🎖️ **Niveles/XP** con anuncio de ascensos.
- 📈 **Reportes con exportación CSV** y análisis de actividad.

### Comandos Premium destacados

| Comando | Qué hace |
|---|---|
| `/faq palabra \| respuesta` | Crea una auto-respuesta |
| `/programar 18:30 \| texto` | Mensaje programado (una vez) |
| `/programar 6h \| texto` | Mensaje recurrente |
| `/programados` · `/cancelprog <id>` | Listar / cancelar |
| `/nochehoras 23 7` | Configura el modo nocturno |
| `/fban` · `/unfban` · `/fbanlist` | Lista negra global |
| `/nivel` · `/reporte` | Tu nivel / reporte CSV |

## 💳 Sistema Premium (dos métodos)

**Método A — Licencias**
- Admin genera códigos: `/createlicense 5 30` (5 licencias de 30 días).
- Usuario las canjea en su grupo: `/redeem GEST-XXXX-XXXX-XXXX`.
- Verificación en BD, fecha de expiración, **protección anti-doble-canje**
  (código único + transacción) y revocación (`/revokelicense`).

**Método B — Telegram Stars**
- `/premium` → botón ⭐ → factura en Stars (`XTR`).
- `pre_checkout` valida y `successful_payment` activa Premium y guarda el pago
  (idempotente por `telegram_payment_charge_id`).
- Renovación automática marcada en la suscripción.

## 🔐 Seguridad

- Cifrado **Fernet** para datos sensibles (`FERNET_KEY`).
- **Rate limiting** en comandos sensibles (p. ej. `/redeem`: 5/min).
- Permisos por decoradores (admin del producto / admin de grupo).
- Anti-doble-canje y pagos idempotentes.
- Secretos en `.env` (fuera del repo, ver `.gitignore`).

## 💰 Modelo de negocio

| Plan | Precio | Incluye |
|---|---|---|
| **Gratis** | 0 | Moderación, bienvenidas, reglas, estadísticas básicas |
| **Premium** | `PREMIUM_STARS_PRICE`⭐ / `PREMIUM_DAYS` días | IA, reportes+export, niveles, programados, dashboard |

Ideas de monetización: venta directa de licencias (transferencia/PayPal y
entregas el código), pago in-app con Stars (Telegram reparte ingresos), y
planes anuales con descuento. Define el precio en `.env`.

## 🚀 Puesta en marcha

```cmd
python -m pip install -r requirements.txt
copy .env.example .env
```
Edita `.env`:
- `BOT_TOKEN` (de @BotFather)
- `ADMIN_IDS` (tu ID de Telegram; pídelo a @userinfobot)
- `DATABASE_URL` (SQLite por defecto; PostgreSQL en producción)
- `FERNET_KEY` (genera una: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)

Ejecuta:
```cmd
python main.py
```

### PostgreSQL en producción
```
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/bot_gestor
```
Las tablas se crean solas al arrancar. Para migraciones formales, se recomienda
añadir Alembic.

### Despliegue en VPS Linux
- Crea un entorno virtual e instala `requirements.txt`.
- Configura las variables de entorno (no subas `.env`).
- Ejecuta con un servicio **systemd** o **pm2/supervisor** para reinicio
  automático. (El bot usa polling; no requiere abrir puertos.)

## 🧪 Pruebas

```cmd
python smoke_test.py
```
Cubre BD, licencias (incl. anti-doble-canje), suscripciones (extensión y
expiración), ajustes, estadísticas, cifrado real, rate limiting, filtros de
moderación e IA heurística. Corre sobre SQLite en memoria (sin token).

## 🗺️ Hoja de ruta (para completar el producto)

- **Dashboard web** (FastAPI + login JWT + gráficos en tiempo real). La capa
  `services/` ya expone toda la lógica; el dashboard solo la consume.
- **IA con modelo externo**: sustituir `moderation/ai.classify` por una llamada
  a una API (la interfaz ya está aislada).
- **Mensajes/encuestas programadas** con persistencia (reutilizar patrón de
  `JobQueue`).
- **Alembic** para migraciones de esquema.
- **Redis** para rate limiting y caché en despliegues multiproceso.
