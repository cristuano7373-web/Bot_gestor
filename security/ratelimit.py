"""Rate limiting en memoria (ventana deslizante) por usuario y acción.

Protege comandos sensibles (p. ej. /redeem) contra abuso/fuerza bruta.
Para despliegues multiproceso se recomienda respaldar con Redis; esta versión
en memoria cubre un proceso único (lo habitual en un VPS pequeño).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[int, str], deque] = defaultdict(deque)

    def allow(self, user_id: int, action: str, *, limit: int, window: float) -> bool:
        """True si la acción está permitida; False si supera el límite."""
        key = (user_id, action)
        now = time.time()
        dq = self._hits[key]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True

    def retry_after(self, user_id: int, action: str, window: float) -> int:
        dq = self._hits.get((user_id, action))
        if not dq:
            return 0
        return max(0, int(window - (time.time() - dq[0])))


rate_limiter = RateLimiter()
