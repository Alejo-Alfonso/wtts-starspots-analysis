"""Modelos de objetivos/secuencias y selección de siguiente objetivo."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from . import astro
from .config import SiteConfig


class ExposureSpec(BaseModel):
    image_type: Literal["Light", "Dark", "Bias", "Flat"] = "Light"
    filter: Optional[str] = None
    exposure_s: float = Field(gt=-1, le=3600)
    count: int = Field(1, ge=1, le=1000)
    binning: int = Field(1, ge=1, le=4)


class Target(BaseModel):
    name: str
    ra_h: Optional[float] = Field(None, ge=0, lt=24)  # None => calibración (sin apuntado)
    dec_deg: Optional[float] = Field(None, ge=-90, le=90)
    exposures: list[ExposureSpec]
    priority: int = Field(5, ge=1, le=10)  # 10 = máxima
    min_altitude_deg: float = 30.0
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None

    @model_validator(mode="after")
    def _coords(self):
        if (self.ra_h is None) != (self.dec_deg is None):
            raise ValueError("ra_h y dec_deg deben darse juntos")
        for e in self.exposures:
            if e.image_type != "Bias" and e.exposure_s <= 0:
                raise ValueError("exposure_s debe ser > 0 (excepto Bias)")
        return self


class SequenceOptions(BaseModel):
    require_dark: bool = True  # esperar a que el Sol esté bajo el límite
    sun_altitude_limit_deg: float = -12.0
    auto_open: bool = True
    autofocus_at_start: bool = True
    close_when_done: bool = True


def airmass(alt_deg: float) -> Optional[float]:
    if alt_deg <= 0:
        return None
    import math
    # Pickering (2002)
    return 1.0 / math.sin(math.radians(alt_deg + 244.0 / (165.0 + 47.0 * alt_deg**1.1)))


def next_target(pending: list[Target], site: SiteConfig, now: Optional[datetime] = None) -> Optional[Target]:
    """Mayor prioridad entre los objetivos observables ahora; desempata por mayor altitud.
    Las calibraciones (sin coordenadas) se consideran siempre observables."""
    now = now or datetime.now(timezone.utc)
    best: tuple[tuple[int, float], Target] | None = None
    for t in pending:
        if t.not_before and now < t.not_before:
            continue
        if t.not_after and now > t.not_after:
            continue
        if t.ra_h is None:
            alt = 90.0
        else:
            alt, _ = astro.altaz(t.ra_h, t.dec_deg, site, now)
            if alt < t.min_altitude_deg:
                continue
        key = (t.priority, alt)
        if best is None or key > best[0]:
            best = (key, t)
    return best[1] if best else None
