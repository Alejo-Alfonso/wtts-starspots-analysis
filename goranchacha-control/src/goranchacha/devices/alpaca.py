"""Backend ASCOM Alpaca (HTTP/JSON). Funciona con drivers ASCOM expuestos por la
ASCOM Remote Server / Alpaca nativo (https://ascom-standards.org/api/)."""
from __future__ import annotations

import itertools
import time
from typing import Callable, Optional

import httpx
import numpy as np

from .base import (Camera, Dome, DeviceError, FilterWheel, Focuser, Mount, ShutterState, Weather,
                   WeatherReading)

_SHUTTER = {0: ShutterState.OPEN, 1: ShutterState.CLOSED, 2: ShutterState.OPENING,
            3: ShutterState.CLOSING, 4: ShutterState.ERROR}
_ids = itertools.count(1)


class AlpacaDevice:
    DEVICE_TYPE = ""

    def __init__(self, url: str, device_number: int = 0, client: httpx.Client | None = None,
                 timeout: float = 10.0):
        self._base = f"{url.rstrip('/')}/api/v1/{self.DEVICE_TYPE}/{device_number}"
        self._http = client or httpx.Client(timeout=timeout)

    def _call(self, method: str, name: str, data: dict | None = None):
        params = {"ClientID": 1, "ClientTransactionID": next(_ids)}
        try:
            if method == "GET":
                r = self._http.get(f"{self._base}/{name}", params=params)
            else:
                r = self._http.put(f"{self._base}/{name}", data={**params, **(data or {})})
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DeviceError(f"Alpaca {self.DEVICE_TYPE}/{name}: {exc}") from exc
        if body.get("ErrorNumber", 0) != 0:
            raise DeviceError(f"Alpaca {self.DEVICE_TYPE}/{name}: [{body['ErrorNumber']}] {body.get('ErrorMessage','')}")
        return body.get("Value")

    def get(self, name: str):
        return self._call("GET", name)

    def put(self, name: str, **data):
        return self._call("PUT", name, data)

    def connect(self) -> None:
        self.put("connected", Connected="true")

    def disconnect(self) -> None:
        self.put("connected", Connected="false")

    @property
    def connected(self) -> bool:
        try:
            return bool(self.get("connected"))
        except DeviceError:
            return False


class AlpacaMount(AlpacaDevice, Mount):
    DEVICE_TYPE = "telescope"
    ra_h = property(lambda s: float(s.get("rightascension")))
    dec_deg = property(lambda s: float(s.get("declination")))
    slewing = property(lambda s: bool(s.get("slewing")))
    at_park = property(lambda s: bool(s.get("atpark")))
    tracking = property(lambda s: bool(s.get("tracking")))

    def set_tracking(self, on): self.put("tracking", Tracking=str(bool(on)).lower())
    def slew_to(self, ra_h, dec_deg): self.put("slewtocoordinatesasync", RightAscension=ra_h, Declination=dec_deg)
    def abort_slew(self): self.put("abortslew")
    def park(self): self.put("park")
    def unpark(self): self.put("unpark")


class AlpacaCamera(AlpacaDevice, Camera):
    DEVICE_TYPE = "camera"
    ccd_temperature_c = property(lambda s: float(s.get("ccdtemperature")))
    cooler_on = property(lambda s: bool(s.get("cooleron")))
    binning = property(lambda s: int(s.get("binx")))

    @property
    def sensor_size(self):
        return int(self.get("cameraxsize")), int(self.get("cameraysize"))

    def set_cooler(self, on, setpoint_c=None):
        if setpoint_c is not None:
            self.put("setccdtemperature", SetCCDTemperature=setpoint_c)
        self.put("cooleron", CoolerOn=str(bool(on)).lower())

    def set_binning(self, n):
        self.put("binx", BinX=n)
        self.put("biny", BinY=n)

    def expose(self, duration_s, light=True, should_abort=lambda: False, progress=lambda f: None):
        self.put("startexposure", Duration=duration_s, Light=str(bool(light)).lower())
        t0 = time.monotonic()
        while not self.get("imageready"):
            if should_abort():
                self.put("abortexposure")
                return None
            progress(min((time.monotonic() - t0) / max(duration_s, 1e-3), 0.99))
            time.sleep(0.25)
        arr = np.array(self.get("imagearray"))  # JSON: [x][y]; ver nota en README (ImageBytes)
        return arr.T.astype(np.uint16) if arr.ndim == 2 else arr


class AlpacaFilterWheel(AlpacaDevice, FilterWheel):
    DEVICE_TYPE = "filterwheel"
    names = property(lambda s: list(s.get("names")))

    @property
    def position(self) -> int:
        return int(self.get("position"))

    def set_position(self, pos):
        self.put("position", Position=pos)
        deadline = time.monotonic() + 60
        while self.position == -1:  # -1 = en movimiento
            if time.monotonic() > deadline:
                raise DeviceError("Timeout moviendo la rueda de filtros")
            time.sleep(0.2)


class AlpacaFocuser(AlpacaDevice, Focuser):
    DEVICE_TYPE = "focuser"
    position = property(lambda s: int(s.get("position")))
    max_step = property(lambda s: int(s.get("maxstep")))
    moving = property(lambda s: bool(s.get("ismoving")))

    @property
    def temperature_c(self) -> Optional[float]:
        try:
            return float(self.get("temperature"))
        except DeviceError:
            return None

    def move_to(self, pos): self.put("move", Position=int(pos))


class AlpacaDome(AlpacaDevice, Dome):
    DEVICE_TYPE = "dome"
    azimuth_deg = property(lambda s: float(s.get("azimuth")))
    slewing = property(lambda s: bool(s.get("slewing")))
    shutter = property(lambda s: _SHUTTER.get(int(s.get("shutterstatus")), ShutterState.ERROR))

    def open_shutter(self): self.put("openshutter")
    def close_shutter(self): self.put("closeshutter")
    def slew_to_azimuth(self, az_deg): self.put("slewtoazimuth", Azimuth=az_deg)
    def park(self): self.put("park")


class AlpacaWeather(AlpacaDevice, Weather):
    DEVICE_TYPE = "observingconditions"
    _MAP = dict(temperature_c="temperature", humidity_pct="humidity", pressure_hpa="pressure",
                wind_speed_ms="windspeed", wind_gust_ms="windgust", dew_point_c="dewpoint",
                cloud_cover_pct="cloudcover", rain_rate_mm_h="rainrate")

    def read(self) -> WeatherReading:
        vals = {}
        for field, prop in self._MAP.items():
            try:
                vals[field] = float(self.get(prop))
            except DeviceError:
                vals[field] = None  # propiedad no implementada por el sensor
        return WeatherReading(timestamp=time.time(), **vals)
