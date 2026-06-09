"""Modelos de base de datos de Bot_Gestor.

Tablas:
  User           - usuarios de Telegram conocidos por el bot
  Group          - grupos donde está el bot
  GroupSettings  - configuración por grupo (clave/valor flexible)
  License        - licencias canjeables (método A)
  Subscription   - estado Premium por grupo (licencia o Stars)
  Payment        - historial de pagos (Telegram Stars)
  MessageStat    - actividad diaria por grupo/usuario (estadísticas)
  Warn           - advertencias de moderación
  UserLevel      - XP y nivel por usuario/grupo
  AuditLog       - registro de acciones sensibles
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user_id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    lang: Mapped[str] = mapped_column(String(5), default="es")
    is_bot_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram chat_id
    title: Mapped[str | None] = mapped_column(String(256))
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GroupSettings(Base):
    __tablename__ = "group_settings"
    __table_args__ = (UniqueConstraint("group_id", "key", name="uq_group_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str | None] = mapped_column(Text)


class License(Base):
    """Licencia canjeable (método A). Código único, un solo uso."""
    __tablename__ = "licenses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    days: Mapped[int] = mapped_column(Integer, default=30)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    redeemed: Mapped[bool] = mapped_column(Boolean, default=False)
    redeemed_by: Mapped[int | None] = mapped_column(BigInteger)
    redeemed_group: Mapped[int | None] = mapped_column(BigInteger)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Subscription(Base):
    """Estado Premium de un grupo. Una fila por grupo."""
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(16), default="free")   # free | premium
    source: Mapped[str | None] = mapped_column(String(16))          # license | stars
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Payment(Base):
    """Historial de pagos (Telegram Stars)."""
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    group_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    amount: Mapped[int] = mapped_column(Integer)                    # en Stars (XTR)
    currency: Mapped[str] = mapped_column(String(8), default="XTR")
    telegram_charge_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    payload: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="paid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageStat(Base):
    """Actividad agregada por día / grupo / usuario."""
    __tablename__ = "message_stats"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", "day", name="uq_stat_day"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)        # YYYY-MM-DD
    messages: Mapped[int] = mapped_column(Integer, default=0)
    is_new_member: Mapped[bool] = mapped_column(Boolean, default=False)


class Warn(Base):
    __tablename__ = "warns"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_warn"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[str] = mapped_column(Text, default="[]")        # JSON


class UserLevel(Base):
    """XP y nivel por usuario en cada grupo (función Premium)."""
    __tablename__ = "user_levels"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_level"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)


class AuditLog(Base):
    """Registro de acciones sensibles (licencias, pagos, bans...)."""
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScheduledMessage(Base):
    """Mensaje programado (único o recurrente) por grupo — Premium."""
    __tablename__ = "scheduled_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    text: Mapped[str] = mapped_column(Text)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_s: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FaqEntry(Base):
    """Respuesta automática por palabra clave — Premium."""
    __tablename__ = "faq_entries"
    __table_args__ = (UniqueConstraint("group_id", "keyword", name="uq_faq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    keyword: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str] = mapped_column(Text)


class FedBan(Base):
    """Lista negra global por dueño (federación) — Premium."""
    __tablename__ = "fed_bans"
    __table_args__ = (UniqueConstraint("owner_id", "user_id", name="uq_fedban"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
