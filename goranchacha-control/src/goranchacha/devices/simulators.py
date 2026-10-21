"""Simuladores de todos los equipos para desarrollo, pruebas y capacitación."""
from __future__ import annotations

import hashlib
import math
import time
from typing import Callable, Optional

import numpy as np

from .base import (Camera, Devices, DeviceError, Dome, FilterWheel, Focuser, Mount,
                   ShutterState, Weather, WeatherReading)


class SimWorld:
    """Estado compartido para que la cámara 'vea' lo que hace la montura y el enfocador."""

    BEST_FOCUS = 12000

    def __init__(self, time_scale: float = 1.0, filter_names: list[str] | None = None):
        self.time_scale = max(time_scale, 1e-6)
        self.filter_names = filter_names or ["L", "B", "V", "R", "I"]
        self.mount: SimMount | None = None
        self.focuser: SimFocuser | None = None
        self.filterwheel: SimFilterWheel | None = None

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds / self.time_scale)


class _SimBase:
    def __init__(self, world: SimWorld):
        self.world = world
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _need(self) -> None:
        if not self._connected:
            raise DeviceError("Equipo no conectado")


class SimMount(_SimBase, Mount):
    SLEW_RATE_DEG_S = 3.0

    def __init__(self, world: SimWorld):
        super().__init__(world)
        self._ra, self._dec = 0.0, 0.0
        self._parked = True
        self._tracking = False
        self._target: tuple[float, float] | None = None
        self._slew_end = 0.0

    def _update(self) -> None:
        if self._target and time.monotonic() >= self._slew_end:
            self._ra, self._dec = self._target
            self._target = None

    @property
    def ra_h(self) -> float:
        self._need(); self._update()
        return self._ra

    @property
    def dec_deg(self) -> float:
        self._need(); self._update()
        return self._dec

    @property
    def slewing(self) -> bool:
        self._need(); self._update()
        return self._target is not None

    @property
    def at_park(self) -> bool:
        return self._parked

    @property
    def tracking(self) -> bool:
        return self._tracking

    def set_tracking(self, on: bool) -> None:
        self._need()
        if on and self._parked:
            raise DeviceError("La montura está estacionada")
        self._tracking = on

    def slew_to(self, ra_h: float, dec_deg: float) -> None:
        self._need()
        if self._parked:
            raise DeviceError("La montura está estacionada")
        if not (0 <= ra_h < 24 and -90 <= dec_deg <= 90):
            raise DeviceError("Coordenadas fuera de rango")
        self._update()
        dist = math.hypot((ra_h - self._ra) * 15, dec_deg - self._dec)
        self._target = (ra_h, dec_deg)
        self._slew_end = time.monotonic() + dist / self.SLEW_RATE_DEG_S / self.world.time_scale

    def abort_slew(self) -> None:
        self._need(); self._update()
        if self._target:
            self._target = None  # queda donde estaba (aprox.)

    def park(self) -> None:
        self._need()
        self._target = (0.0, 0.0)
        self._slew_end = time.monotonic() + 3 / self.world.time_scale
        self._tracking = False
        self._parked = True

    def unpark(self) -> None:
        self._need()
        self._parked = False


class SimFilterWheel(_SimBase, FilterWheel):
    def __init__(self, world: SimWorld):
        super().__init__(world)
        self._pos = 0
        world.filterwheel = self

    @property
    def names(self) -> list[str]:
        return list(self.world.filter_names)

    @property
    def position(self) -> int:
        return self._pos

    def set_position(self, pos: int) -> None:
        self._need()
        if not 0 <= pos < len(self.names):
            raise DeviceError(f"Posición de filtro inválida: {pos}")
        if pos != self._pos:
            self.world.sleep(2.0)
        self._pos = pos


class SimFocuser(_SimBase, Focuser):
    SPEED = 500.0  # pasos/s

    def __init__(self, world: SimWorld, start: int = 11500):
        super().__init__(world)
        self._pos = start
        self._target: Optional[int] = None
        self._end = 0.0
        self.temp_c = 12.0
        world.focuser = self

    def _update(self) -> None:
        if self._target is not None and time.monotonic() >= self._end:
            self._pos, self._target = self._target, None

    @property
    def position(self) -> int:
        self._update()
        return self._pos

    @property
    def max_step(self) -> int:
        return 30000

    @property
    def temperature_c(self) -> Optional[float]:
        return self.temp_c

    @property
    def moving(self) -> bool:
        self._update()
        return self._target is not None

    def move_to(self, pos: int) -> None:
        self._need(); self._update()
        if not 0 <= pos <= self.max_step:
            raise DeviceError("Posición de enfocador fuera de rango")
        self._end = time.monotonic() + abs(pos - self._pos) / self.SPEED / self.world.time_scale
        self._target = int(pos)


class SimDome(_SimBase, Dome):
    SHUTTER_TIME_S = 20.0
    DOME_RATE = 4.0  # grados/s

    def __init__(self, world: SimWorld):
        super().__init__(world)
        self._shutter = ShutterState.CLOSED
        self._shutter_target: Optional[ShutterState] = None
        self._shutter_end = 0.0
        self._az = 0.0
        self._az_target: Optional[float] = None
        self._az_end = 0.0

    def _update(self) -> None:
        now = time.monotonic()
        if self._shutter_target and now >= self._shutter_end:
            self._shutter, self._shutter_target = self._shutter_target, None
        if self._az_target is not None and now >= self._az_end:
            self._az, self._az_target = self._az_target, None

    @property
    def shutter(self) -> ShutterState:
        self._update()
        if self._shutter_target is ShutterState.OPEN:
            return ShutterState.OPENING
        if self._shutter_target is ShutterState.CLOSED:
            return ShutterState.CLOSING
        return self._shutter

    def open_shutter(self) -> None:
        self._need(); self._update()
        if self._shutter is not ShutterState.OPEN:
            self._shutter_target = ShutterState.OPEN
            self._shutter_end = time.monotonic() + self.SHUTTER_TIME_S / self.world.time_scale

    def close_shutter(self) -> None:
        self._need(); self._update()
        if self._shutter is not ShutterState.CLOSED:
            self._shutter_target = ShutterState.CLOSED
            self._shutter_end = time.monotonic() + self.SHUTTER_TIME_S / self.world.time_scale

    @property
    def azimuth_deg(self) -> float:
        self._update()
        return self._az

    @property
    def slewing(self) -> bool:
        self._update()
        return self._az_target is not None

    def slew_to_azimuth(self, az_deg: float) -> None:
        self._need(); self._update()
        az = az_deg % 360
        diff = abs((az - self._az + 180) % 360 - 180)
        self._az_target = az
        self._az_end = time.monotonic() + diff / self.DOME_RATE / self.world.time_scale

    def park(self) -> None:
        self.slew_to_azimuth(0.0)


class SimWeather(_SimBase, Weather):
    def __init__(self, world: SimWorld):
        super().__init__(world)
        self.values = dict(temperature_c=12.0, humidity_pct=55.0, pressure_hpa=740.0, wind_speed_ms=3.0,
                           wind_gust_ms=5.0, dew_point_c=3.0, cloud_cover_pct=10.0, rain_rate_mm_h=0.0)
        self.fail = False  # simula caída del sensor

    def set(self, **kw) -> None:
        self.values.update(kw)

    def read(self) -> WeatherReading:
        self._need()
        if self.fail:
            raise DeviceError("Sensor meteorológico sin respuesta")
        return WeatherReading(timestamp=time.time(), **self.values)


class SimCamera(_SimBase, Camera):
    W, H = 512, 512

    def __init__(self, world: SimWorld):
        super().__init__(world)
        self._cooler = False
        self._setpoint = -20.0
        self._temp = 15.0
        self._bin = 1
        self._rng = np.random.default_rng(1234)

    @property
    def sensor_size(self) -> tuple[int, int]:
        return self.W, self.H

    @property
    def ccd_temperature_c(self) -> float:
        # enfriamiento simple dependiente del tiempo simulado
        target = self._setpoint if self._cooler else 15.0
        self._temp += (target - self._temp) * 0.2
        return round(self._temp, 2)

    @property
    def cooler_on(self) -> bool:
        return self._cooler

    def set_cooler(self, on: bool, setpoint_c: Optional[float] = None) -> None:
        self._need()
        self._cooler = on
        if setpoint_c is not None:
            self._setpoint = setpoint_c

    @property
    def binning(self) -> int:
        return self._bin

    def set_binning(self, n: int) -> None:
        if n not in (1, 2, 3, 4):
            raise DeviceError("Binning no soportado")
        self._bin = n

    def _starfield(self, ra: float, dec: float, sigma: float) -> np.ndarray:
        seed = int(hashlib.sha1(f"{ra:.2f}{dec:.1f}".encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        n = 25
        xs, ys = rng.uniform(30, self.W - 30, n), rng.uniform(30, self.H - 30, n)
        flux = 20000 * rng.pareto(1.5, n).clip(0.05, 6)
        yy, xx = np.mgrid[0 : self.H, 0 : self.W]
        img = np.zeros((self.H, self.W))
        for x, y, f in zip(xs, ys, flux):
            r2 = (xx - x) ** 2 + (yy - y) ** 2
            m = r2 < (6 * sigma) ** 2
            img[m] += f / (2 * math.pi * sigma**2) * np.exp(-r2[m] / (2 * sigma**2))
        return img

    def expose(self, duration_s, light=True, should_abort=lambda: False, progress=lambda f: None):
        self._need()
        remaining = duration_s
        step = 0.25
        while remaining > 0:
            if should_abort():
                return None
            dt = min(step, remaining)
            self.world.sleep(dt)
            remaining -= dt
            progress(1 - remaining / duration_s if duration_s else 1.0)
        if should_abort():
            return None
        img = np.full((self.H, self.W), 1000.0)
        img += self._rng.normal(0, 8, img.shape)  # ruido de lectura
        if light:
            w = self.world
            sigma = 1.5
            if w.focuser is not None:
                dx = (w.focuser.position - SimWorld.BEST_FOCUS) / 150.0
                sigma = math.sqrt(1.5**2 + dx**2)
            ra = w.mount.ra_h if w.mount else 0.0
            dec = w.mount.dec_deg if w.mount else 0.0
            img += self._starfield(ra, dec, sigma) * min(duration_s, 60) / 10
            img += 0.5 * duration_s  # fondo de cielo
            img += self._rng.normal(0, 1, img.shape) * np.sqrt(np.clip(img, 0, None)) * 0.05
        else:
            img += 0.02 * duration_s  # corriente oscura
        return np.clip(img, 0, 65535).astype(np.uint16)


def build_simulated_devices(time_scale: float = 1.0, filter_names: list[str] | None = None) -> Devices:
    world = SimWorld(time_scale, filter_names)
    mount = SimMount(world)
    world.mount = mount
    return Devices(mount=mount, camera=SimCamera(world), filterwheel=SimFilterWheel(world),
                   focuser=SimFocuser(world), dome=SimDome(world), weather=SimWeather(world))
