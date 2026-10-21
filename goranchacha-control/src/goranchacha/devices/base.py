"""Interfaces abstractas de los equipos. Cada backend (simulador, Alpaca...) las implementa."""
from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


class DeviceError(Exception):
    """Error de comunicación o de operación con un equipo."""


class ShutterState(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    OPENING = "opening"
    CLOSING = "closing"
    ERROR = "error"


@dataclass
class WeatherReading:
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    pressure_hpa: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    wind_gust_ms: Optional[float] = None
    dew_point_c: Optional[float] = None
    cloud_cover_pct: Optional[float] = None
    rain_rate_mm_h: Optional[float] = None
    timestamp: float = 0.0  # epoch de la medición


class Device(abc.ABC):
    @abc.abstractmethod
    def connect(self) -> None: ...

    @abc.abstractmethod
    def disconnect(self) -> None: ...

    @property
    @abc.abstractmethod
    def connected(self) -> bool: ...


class Mount(Device):
    @property
    @abc.abstractmethod
    def ra_h(self) -> float: ...

    @property
    @abc.abstractmethod
    def dec_deg(self) -> float: ...

    @property
    @abc.abstractmethod
    def slewing(self) -> bool: ...

    @property
    @abc.abstractmethod
    def at_park(self) -> bool: ...

    @property
    @abc.abstractmethod
    def tracking(self) -> bool: ...

    @abc.abstractmethod
    def set_tracking(self, on: bool) -> None: ...

    @abc.abstractmethod
    def slew_to(self, ra_h: float, dec_deg: float) -> None:
        """Inicia el apuntado (no bloquea)."""

    @abc.abstractmethod
    def abort_slew(self) -> None: ...

    @abc.abstractmethod
    def park(self) -> None: ...

    @abc.abstractmethod
    def unpark(self) -> None: ...


class Camera(Device):
    @property
    @abc.abstractmethod
    def sensor_size(self) -> tuple[int, int]:
        """(ancho, alto) en píxeles."""

    @property
    @abc.abstractmethod
    def ccd_temperature_c(self) -> float: ...

    @property
    @abc.abstractmethod
    def cooler_on(self) -> bool: ...

    @abc.abstractmethod
    def set_cooler(self, on: bool, setpoint_c: Optional[float] = None) -> None: ...

    @property
    @abc.abstractmethod
    def binning(self) -> int: ...

    @abc.abstractmethod
    def set_binning(self, n: int) -> None: ...

    @abc.abstractmethod
    def expose(
        self,
        duration_s: float,
        light: bool = True,
        should_abort: Callable[[], bool] = lambda: False,
        progress: Callable[[float], None] = lambda f: None,
    ) -> Optional[np.ndarray]:
        """Exposición bloqueante. Devuelve la imagen (alto, ancho) o None si se abortó."""


class FilterWheel(Device):
    @property
    @abc.abstractmethod
    def names(self) -> list[str]: ...

    @property
    @abc.abstractmethod
    def position(self) -> int: ...

    @abc.abstractmethod
    def set_position(self, pos: int) -> None:
        """Mueve y espera a que termine."""


class Focuser(Device):
    @property
    @abc.abstractmethod
    def position(self) -> int: ...

    @property
    @abc.abstractmethod
    def max_step(self) -> int: ...

    @property
    @abc.abstractmethod
    def temperature_c(self) -> Optional[float]: ...

    @property
    @abc.abstractmethod
    def moving(self) -> bool: ...

    @abc.abstractmethod
    def move_to(self, pos: int) -> None:
        """Inicia el movimiento (no bloquea)."""


class Dome(Device):
    @property
    @abc.abstractmethod
    def shutter(self) -> ShutterState: ...

    @abc.abstractmethod
    def open_shutter(self) -> None: ...

    @abc.abstractmethod
    def close_shutter(self) -> None: ...

    @property
    @abc.abstractmethod
    def azimuth_deg(self) -> float: ...

    @property
    @abc.abstractmethod
    def slewing(self) -> bool: ...

    @abc.abstractmethod
    def slew_to_azimuth(self, az_deg: float) -> None: ...

    @abc.abstractmethod
    def park(self) -> None: ...


class Weather(Device):
    @abc.abstractmethod
    def read(self) -> WeatherReading: ...


@dataclass
class Devices:
    mount: Mount
    camera: Camera
    filterwheel: FilterWheel
    focuser: Focuser
    dome: Dome
    weather: Weather

    def all(self) -> list[Device]:
        return [self.mount, self.camera, self.filterwheel, self.focuser, self.dome, self.weather]
