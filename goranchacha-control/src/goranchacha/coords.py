"""Conversión de coordenadas escritas por el operador (decimal o sexagesimal)."""
from __future__ import annotations

import re


def _parse(text: str) -> float:
    t = text.strip().lower().replace("h", ":").replace("m", ":").replace("s", "").replace("°", ":").replace("d", ":")
    t = t.replace("'", ":").replace('"', "")
    sign = -1.0 if t.startswith("-") else 1.0
    parts = [p for p in re.split(r"[:\s]+", t.lstrip("+-")) if p]
    if not parts or len(parts) > 3:
        raise ValueError(f"Coordenada inválida: {text!r}")
    vals = [float(p) for p in parts]
    if any(v < 0 for v in vals) or (len(vals) > 1 and any(v >= 60 for v in vals[1:])):
        raise ValueError(f"Coordenada inválida: {text!r}")
    return sign * sum(v / 60**i for i, v in enumerate(vals))


def parse_ra_hours(text: str) -> float:
    v = _parse(text)
    if not 0 <= v < 24:
        raise ValueError("AR fuera de rango (0-24 h)")
    return v


def parse_dec_degrees(text: str) -> float:
    v = _parse(text)
    if not -90 <= v <= 90:
        raise ValueError("Dec fuera de rango (-90 a +90)")
    return v


def format_ra(h: float) -> str:
    s = round(h * 3600, 1)
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:04.1f}"


def format_dec(d: float) -> str:
    sign = "-" if d < 0 else "+"
    s = round(abs(d) * 3600)
    return f"{sign}{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
