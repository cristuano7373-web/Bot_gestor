"""Lógica del modo nocturno (Premium): ¿está el grupo en horas de cierre?

Función pura para poder testearla. Maneja ventanas que cruzan medianoche
(p. ej. de 23:00 a 07:00).
"""
from __future__ import annotations


def is_night(hour: int, start: int, end: int) -> bool:
    """True si `hour` está dentro de la ventana [start, end).

    - start == end -> nunca (ventana vacía).
    - start < end  -> ventana normal (p. ej. 1 a 6).
    - start > end  -> ventana que cruza medianoche (p. ej. 23 a 7).
    """
    hour %= 24
    start %= 24
    end %= 24
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end
