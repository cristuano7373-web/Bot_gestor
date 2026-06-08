"""Filtros de moderación: antiflood, anti-enlaces, anti-palabras y antispam.

Funciones puras (fáciles de testear) + un FloodTracker en memoria.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque

_URL_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/|@[A-Za-z0-9_]{4,})", re.I)


def has_link(text: str, entities=None) -> bool:
    """Detecta enlaces por entidades de Telegram o por patrón en el texto."""
    if entities:
        for e in entities:
            if getattr(e, "type", None) in ("url", "text_link", "mention"):
                return True
    return bool(text and _URL_RE.search(text))


def contains_badword(text: str, words: list[str]) -> bool:
    if not text or not words:
        return False
    low = f" {text.lower()} "
    for w in words:
        w = w.lower().strip()
        if w and (w in low):
            return True
    return False


def is_spam(text: str) -> bool:
    """Heurística rápida de spam (sin IA): exceso de enlaces, mayúsculas o repetición."""
    if not text:
        return False
    t = text.strip()
    # Muchos enlaces
    if len(_URL_RE.findall(t)) >= 2:
        return True
    # Texto muy largo casi todo en mayúsculas
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= 25 and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return True
    # Caracteres repetidos en exceso (aaaaaaa, !!!!!!!)
    if re.search(r"(.)\1{9,}", t):
        return True
    return False


class FloodTracker:
    """Cuenta mensajes por (grupo, usuario) en una ventana deslizante."""
    def __init__(self) -> None:
        self._hits: dict[tuple[int, int], deque] = defaultdict(deque)

    def hit(self, group_id: int, user_id: int, *, count: int, window: float) -> bool:
        """Registra un mensaje. True si el usuario superó el límite (flood)."""
        key = (group_id, user_id)
        now = time.time()
        dq = self._hits[key]
        dq.append(now)
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= count:
            dq.clear()
            return True
        return False


flood_tracker = FloodTracker()
