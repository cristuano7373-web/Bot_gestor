"""Cifrado de datos sensibles con Fernet (AES-128 autenticado).

Se usa para guardar datos sensibles en BD. La clave viene de FERNET_KEY.
Si no hay clave configurada, se opera en modo "passthrough" (sin cifrar) y se
avisa por log — útil en desarrollo, no recomendado en producción.
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

import config

log = logging.getLogger("bot_gestor")

_fernet: Fernet | None = None
_warned = False


def _get() -> Fernet | None:
    global _fernet, _warned
    if _fernet is None and config.FERNET_KEY:
        try:
            _fernet = Fernet(config.FERNET_KEY.encode())
        except Exception:  # noqa: BLE001
            if not _warned:
                log.error("FERNET_KEY inválida; los datos no se cifrarán.")
                _warned = True
    if _fernet is None and not _warned:
        log.warning("FERNET_KEY no configurada; datos sensibles sin cifrar.")
        _warned = True
    return _fernet


def encrypt(text: str) -> str:
    f = _get()
    if not f or text is None:
        return text
    return f.encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    f = _get()
    if not f or token is None:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        return token


def generate_key() -> str:
    """Genera una clave Fernet nueva (para configurar FERNET_KEY)."""
    return Fernet.generate_key().decode()
