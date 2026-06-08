"""Moderación con IA (función Premium).

Implementación por heurística avanzada lista para usar, con una interfaz
*pluggable*: puedes sustituir `classify` por una llamada a un modelo/much API
(OpenAI, Perspective API, un clasificador propio) sin tocar el resto del bot.

`classify(text)` devuelve un dict:
  {
    "spam": bool, "insult": bool, "suspicious": bool,
    "score": float (0..1),  # riesgo
    "labels": [str, ...],
    "reason": str,
  }
"""
from __future__ import annotations

import re

# Léxico base (ampliable). En producción conviene cargarlo desde BD/archivo
# y/o reemplazar por un modelo entrenado.
_INSULTS = {
    "idiota", "imbecil", "imbécil", "estupido", "estúpido", "tonto", "burro",
    "pendejo", "gilipollas", "subnormal", "mierda", "basura", "inutil", "inútil",
}
_SCAM_PATTERNS = [
    re.compile(r"\b(gana|ganar[aá]s?)\b.*\b(dinero|d[oó]lares|usdt|bitcoin|cripto)\b", re.I),
    re.compile(r"\b(inversi[oó]n|invierte)\b.*\b(garantizad[ao]|x\d+|doble)\b", re.I),
    re.compile(r"\b(retiro|retira)\b.*\b(inmediato|gratis)\b", re.I),
    re.compile(r"(free|gratis).*(nitro|stars|premium)", re.I),
    re.compile(r"(http|t\.me/).{0,40}(airdrop|claim|whatsapp)", re.I),
]
_URL = re.compile(r"(https?://|t\.me/|wa\.me/|@[A-Za-z0-9_]{4,})", re.I)


def classify(text: str) -> dict:
    text = text or ""
    low = text.lower()
    labels: list[str] = []
    score = 0.0

    # Insultos
    words = set(re.findall(r"[a-záéíóúñ]+", low))
    insult = bool(words & _INSULTS)
    if insult:
        labels.append("insulto")
        score += 0.5

    # Estafa / contenido sospechoso
    suspicious = any(p.search(text) for p in _SCAM_PATTERNS)
    if suspicious:
        labels.append("estafa")
        score += 0.6

    # Spam: muchos enlaces o menciones
    links = len(_URL.findall(text))
    spam = links >= 2 or (links >= 1 and suspicious)
    if spam:
        labels.append("spam")
        score += 0.4

    score = min(1.0, score)
    reason = ", ".join(labels) if labels else "ok"
    return {
        "spam": spam,
        "insult": insult,
        "suspicious": suspicious,
        "score": round(score, 2),
        "labels": labels,
        "reason": reason,
    }


def should_act(result: dict, threshold: float = 0.5) -> bool:
    """Decide si la IA debe intervenir según el riesgo."""
    return result["score"] >= threshold
