"""Evaluación de seguridad meteorológica. Diseño fail-safe: sin datos fiables => inseguro."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .config import SafetyConfig
from .devices.base import WeatherReading


@dataclass
class SafetyStatus:
    safe: bool
    reasons: list[str] = field(default_factory=list)
    can_open: bool = False  # seguro y estable el tiempo mínimo
    reading: Optional[WeatherReading] = None


class SafetyMonitor:
    def __init__(self, cfg: SafetyConfig):
        self.cfg = cfg
        self._failures = 0
        self._safe_since: Optional[float] = None
        self.last = SafetyStatus(safe=False, reasons=["Sin lecturas todavía"])

    def evaluate(self, reading: Optional[WeatherReading], now: Optional[float] = None) -> SafetyStatus:
        """`reading=None` indica fallo al leer el sensor."""
        now = time.time() if now is None else now
        c = self.cfg
        reasons: list[str] = []

        if reading is None:
            self._failures += 1
            if self._failures >= c.max_consecutive_failures:
                reasons.append(f"Sensor meteorológico sin respuesta ({self._failures} fallos)")
            elif self.last.reading is not None:
                # fallo transitorio: conservar el último veredicto
                self.last = SafetyStatus(self.last.safe, list(self.last.reasons), self.last.can_open, self.last.reading)
                return self.last
            else:
                reasons.append("Sin lecturas todavía")
        else:
            self._failures = 0
            if reading.timestamp and now - reading.timestamp > c.max_reading_age_s:
                reasons.append(f"Lectura obsoleta ({now - reading.timestamp:.0f} s)")
            if reading.rain_rate_mm_h is None and reading.humidity_pct is None:
                reasons.append("El sensor no reporta lluvia ni humedad")
            if c.rain_closes and (reading.rain_rate_mm_h or 0) > 0:
                reasons.append("Lluvia detectada")
            if reading.wind_speed_ms is not None and reading.wind_speed_ms > c.max_wind_ms:
                reasons.append(f"Viento {reading.wind_speed_ms:.1f} m/s > {c.max_wind_ms}")
            if reading.wind_gust_ms is not None and reading.wind_gust_ms > c.max_gust_ms:
                reasons.append(f"Ráfaga {reading.wind_gust_ms:.1f} m/s > {c.max_gust_ms}")
            if reading.humidity_pct is not None and reading.humidity_pct > c.max_humidity_pct:
                reasons.append(f"Humedad {reading.humidity_pct:.0f}% > {c.max_humidity_pct:.0f}%")
            if reading.temperature_c is not None and reading.dew_point_c is not None:
                margin = reading.temperature_c - reading.dew_point_c
                if margin < c.min_dewpoint_margin_c:
                    reasons.append(f"Margen al punto de rocío {margin:.1f} °C < {c.min_dewpoint_margin_c}")
            if (c.max_cloud_pct is not None and reading.cloud_cover_pct is not None
                    and reading.cloud_cover_pct > c.max_cloud_pct):
                reasons.append(f"Nubosidad {reading.cloud_cover_pct:.0f}% > {c.max_cloud_pct:.0f}%")

        safe = not reasons
        if safe:
            if self._safe_since is None:
                self._safe_since = now
        else:
            self._safe_since = None
        can_open = safe and self._safe_since is not None and (now - self._safe_since) >= c.safe_hold_minutes * 60
        self.last = SafetyStatus(safe, reasons, can_open, reading if reading is not None else self.last.reading)
        return self.last
