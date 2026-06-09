"""Pruebas del núcleo de Bot_Gestor sobre SQLite en memoria (sin token).

Verifica: base de datos, licencias (canje + anti-doble-canje), suscripciones
Premium (activación/extensión/expiración), ajustes, estadísticas, cifrado,
rate limiting, filtros de moderación y la IA heurística.
"""
import asyncio
import os

# Forzar SQLite en memoria ANTES de importar config/módulos.
os.environ.setdefault("BOT_TOKEN", "111:DUMMY")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import config  # noqa: E402
from db.base import create_all, init_engine  # noqa: E402
from services import licenses, subscriptions, settings, stats  # noqa: E402
from services.entities import ensure_user, ensure_group  # noqa: E402
from security import crypto  # noqa: E402
from security.ratelimit import RateLimiter  # noqa: E402
from moderation import ai  # noqa: E402
from moderation.filters import has_link, contains_badword, is_spam, FloodTracker  # noqa: E402


async def test_db_and_entities():
    init_engine("sqlite+aiosqlite:///:memory:")
    await create_all()
    await ensure_user(1, "tokyo", "Tokyo")
    await ensure_group(-100, "Mi Grupo", added_by=1)
    # Idioma por defecto y cambio
    from services.entities import get_lang, set_lang
    assert await get_lang(1) == "es"
    await set_lang(1, "en")
    assert await get_lang(1) == "en"
    print("OK base de datos: tablas creadas, usuario, grupo e idioma")


async def test_licenses_and_premium():
    codes = await licenses.create_licenses(3, 30, created_by=1)
    assert len(codes) == 3 and all(c.startswith("GEST-") for c in codes)

    # Canje válido -> activa Premium
    result = await licenses.redeem(codes[0], user_id=5, group_id=-100)
    assert result["days"] == 30
    assert await subscriptions.is_premium(-100) is True

    # Anti-doble-canje: el mismo código no se puede volver a canjear
    try:
        await licenses.redeem(codes[0], user_id=6, group_id=-200)
        assert False, "debería fallar el segundo canje"
    except licenses.RedeemError:
        pass

    # Código inexistente
    try:
        await licenses.redeem("GEST-XXXX-XXXX-XXXX", 7, -300)
        assert False
    except licenses.RedeemError:
        pass

    # Revocar un código libre, luego no se puede canjear
    assert await licenses.revoke(codes[1]) is True
    try:
        await licenses.redeem(codes[1], 8, -400)
        assert False
    except licenses.RedeemError:
        pass

    # Si el grupo YA es Premium, no se puede canjear otro (no suma días)
    try:
        await licenses.redeem(codes[2], user_id=9, group_id=-100)
        assert False, "no debería permitir canjear estando ya Premium"
    except licenses.RedeemError:
        pass
    print("OK licencias: generación, canje, anti-doble-canje, revocación y bloqueo si ya es Premium")


async def test_subscription_extends_and_expires():
    # Activar de nuevo extiende la fecha (suma días)
    sub1 = await subscriptions.activate_premium(-100, days=30, source="stars",
                                                activated_by=5, auto_renew=True)
    days_after_first = sub1["days_left"]
    sub2 = await subscriptions.activate_premium(-100, days=30, source="stars",
                                                activated_by=5)
    assert sub2["days_left"] >= days_after_first  # se extendió
    assert sub2["active"] is True

    # Forzar expiración: poner fecha en el pasado y expirar
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from db.models import Subscription
    from services import session_scope
    async with session_scope() as s:
        row = (await s.execute(select(Subscription).where(
            Subscription.group_id == -100))).scalar_one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    n = await subscriptions.expire_due()
    assert n >= 1
    assert await subscriptions.is_premium(-100) is False
    print("OK suscripciones: extensión de días y expiración automática")

    # Quitar Premium manualmente
    await subscriptions.activate_premium(-777, days=30, source="license", activated_by=1)
    assert await subscriptions.is_premium(-777) is True
    assert await subscriptions.deactivate_group(-777) is True
    assert await subscriptions.is_premium(-777) is False
    print("OK quitar Premium manualmente (deactivate_group)")


async def test_settings():
    assert await settings.get(-100, "warn_limit") == 3
    await settings.set(-100, "warn_limit", 5)
    assert await settings.get(-100, "warn_limit") == 5
    v = await settings.toggle(-100, "antilinks_enabled")
    assert v == 1
    allset = await settings.get_all(-100)
    assert allset["warn_limit"] == 5 and allset["antilinks_enabled"] == 1
    print("OK ajustes por grupo: get/set/toggle con defaults")


async def test_stats():
    for _ in range(5):
        await stats.record_message(-100, 5)
    await stats.record_message(-100, 6)
    await stats.record_message(-100, 7, new_member=True)
    summ = await stats.group_summary(-100, days=7)
    assert summ["total_messages"] == 6
    assert summ["active_users"] == 2
    assert summ["new_members"] == 1
    rank = await stats.ranking(-100, days=7, limit=5)
    assert rank[0]["user_id"] == 5 and rank[0]["messages"] == 5
    print("OK estadísticas: conteo, activos, nuevos y ranking")


def test_crypto():
    # Configurar una clave real para ejercitar el cifrado de verdad.
    config.FERNET_KEY = crypto.generate_key()
    crypto._fernet = None  # resetear caché para que tome la nueva clave
    crypto._warned = False
    secret = "dato-sensible-123"
    token = crypto.encrypt(secret)
    assert token != secret                 # realmente se cifró
    assert crypto.decrypt(token) == secret  # y se descifra correctamente
    print("OK cifrado: encrypt/decrypt real con Fernet")


def test_ratelimit():
    rl = RateLimiter()
    ok = [rl.allow(1, "redeem", limit=3, window=60) for _ in range(4)]
    assert ok == [True, True, True, False]
    print("OK rate limiting: bloquea tras superar el límite")


def test_moderation_filters():
    assert has_link("mira https://x.com", None) is True
    assert has_link("hola mundo", None) is False
    assert contains_badword("eres un idiota", ["idiota"]) is True
    assert is_spam("GANA DINERO RAPIDO " * 3 + "http://a http://b") is True
    ft = FloodTracker()
    res = [ft.hit(-1, 9, count=4, window=10) for _ in range(4)]
    assert res[-1] is True  # al 4º mensaje detecta flood
    print("OK filtros: enlaces, palabras, spam y antiflood")


def test_ai():
    r = ai.classify("eres un imbecil")
    assert r["insult"] is True and r["score"] >= 0.5
    r2 = ai.classify("Invierte y gana dinero garantizado x10 en cripto http://scam")
    assert r2["suspicious"] is True and ai.should_act(r2)
    r3 = ai.classify("buenos días a todos")
    assert not ai.should_act(r3)
    print("OK IA moderación: insultos, estafa y mensaje normal")


def test_nightmode():
    from moderation.nightmode import is_night
    # Ventana que cruza medianoche 23 -> 7
    assert is_night(23, 23, 7) is True
    assert is_night(3, 23, 7) is True
    assert is_night(8, 23, 7) is False
    # Ventana normal 1 -> 6
    assert is_night(2, 1, 6) is True
    assert is_night(6, 1, 6) is False
    # Vacía
    assert is_night(5, 5, 5) is False
    print("OK modo nocturno: ventanas normales y que cruzan medianoche")


async def test_faq():
    from services import faq
    await faq.set_entry(-100, "Horario", "Atendemos 9 a 18h")
    assert await faq.match(-100, "cual es el horario hoy?") == "Atendemos 9 a 18h"
    assert await faq.match(-100, "hola que tal") is None
    assert await faq.delete(-100, "horario") is True
    print("OK FAQ: alta, coincidencia por palabra y borrado")


async def test_schedules():
    from services import schedules
    from datetime import datetime, timezone
    sid = await schedules.add(-100, "Recordatorio", run_at=None,
                              interval_s=3600, created_by=1)
    rows = await schedules.list_for(-100)
    assert any(r["id"] == sid for r in rows)
    assert await schedules.deactivate(sid, -100) is True
    assert not any(r["id"] == sid for r in await schedules.list_for(-100))
    print("OK programados: alta, listado y desactivación")


async def test_federation():
    from services import federation
    await federation.add_ban(owner_id=1, user_id=999, reason="spam")
    assert await federation.is_banned(1, 999) is True
    assert await federation.is_banned(1, 111) is False
    bans = await federation.list_bans(1)
    assert len(bans) == 1 and bans[0]["user_id"] == 999
    assert await federation.remove_ban(1, 999) is True
    assert await federation.is_banned(1, 999) is False
    print("OK federación: ban global, consulta, listado y quitar")


async def main():
    await test_db_and_entities()
    await test_licenses_and_premium()
    await test_subscription_extends_and_expires()
    await test_settings()
    await test_stats()
    test_crypto()
    test_ratelimit()
    test_moderation_filters()
    test_ai()
    test_nightmode()
    await test_faq()
    await test_schedules()
    await test_federation()
    print("\n✅ TODAS LAS PRUEBAS PASARON")


if __name__ == "__main__":
    asyncio.run(main())
