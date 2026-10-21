"""Configuración del observatorio (YAML -> modelos validados)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field


class SiteConfig(BaseModel):
    name: str = "Observatorio Astronómico Goranchacha (UPTC)"
    # 5°33'N, 73°21'W, 2750 m (dato del usuario; confirmar con coordenadas oficiales).
    latitude_deg: float = 5.55
    longitude_deg: float = -73.35  # este positivo, oeste negativo
    elevation_m: float = 2750.0
    observer: str = "Grupo de Astronomía UPTC"
    telescope: str = "Goranchacha"
    instrument: str = "CCD"


class SafetyConfig(BaseModel):
    max_wind_ms: float = 12.0
    max_gust_ms: float = 15.0
    max_humidity_pct: float = 85.0
    min_dewpoint_margin_c: float = 2.0  # T - Td mínimo
    max_cloud_pct: Optional[float] = 70.0
    rain_closes: bool = True
    sun_altitude_open_limit_deg: float = -6.0  # no abrir con el Sol más alto
    enforce_sun_limit: bool = True
    max_reading_age_s: float = 120.0
    max_consecutive_failures: int = 3  # fallos de lectura -> inseguro (fail-safe)
    safe_hold_minutes: float = 10.0  # tiempo seguro continuo antes de permitir abrir


class AlpacaDeviceConfig(BaseModel):
    url: str = "http://localhost:11111"
    device_number: int = 0


class DevicesConfig(BaseModel):
    backend: Literal["simulator", "alpaca"] = "simulator"
    time_scale: float = 1.0  # solo simulador: >1 acelera el tiempo
    alpaca: dict[str, AlpacaDeviceConfig] = Field(default_factory=dict)
    # claves: mount, camera, filterwheel, focuser, dome, weather
    filter_names: list[str] = ["L", "B", "V", "R", "I"]


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"  # exponer en la red solo con TLS (ver README)
    port: int = 8443
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    token_ttl_minutes: int = 480
    cors_origins: list[str] = []


class Config(BaseModel):
    site: SiteConfig = SiteConfig()
    safety: SafetyConfig = SafetyConfig()
    devices: DevicesConfig = DevicesConfig()
    server: ServerConfig = ServerConfig()
    data_dir: str = "./datos"
    poll_interval_s: float = 5.0
    autofocus_temp_delta_c: float = 1.5

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p


def load_config(path: str | Path | None) -> Config:
    if path is None:
        return Config()
    with open(path, "r", encoding="utf-8") as fh:
        return Config.model_validate(yaml.safe_load(fh) or {})
