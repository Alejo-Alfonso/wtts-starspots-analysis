from __future__ import annotations

from ..config import Config
from .alpaca import (AlpacaCamera, AlpacaDome, AlpacaFilterWheel, AlpacaFocuser, AlpacaMount,
                     AlpacaWeather)
from .base import Devices
from .simulators import build_simulated_devices


def build_devices(cfg: Config) -> Devices:
    d = cfg.devices
    if d.backend == "simulator":
        return build_simulated_devices(d.time_scale, d.filter_names)
    classes = dict(mount=AlpacaMount, camera=AlpacaCamera, filterwheel=AlpacaFilterWheel,
                   focuser=AlpacaFocuser, dome=AlpacaDome, weather=AlpacaWeather)
    missing = [k for k in classes if k not in d.alpaca]
    if missing:
        raise ValueError(f"Faltan dispositivos Alpaca en la configuración: {', '.join(missing)}")
    return Devices(**{k: cls(d.alpaca[k].url, d.alpaca[k].device_number) for k, cls in classes.items()})
