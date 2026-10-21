"""Núcleo de control: orquesta equipos, seguridad, domo esclavizado, exposiciones y secuencias."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import astro
from .autofocus import autofocus
from .config import Config
from .devices.base import Devices, DeviceError, ShutterState
from .fits_io import FrameInfo, save_frame
from .logbook import EventBus
from .safety import SafetyMonitor
from .scheduler import airmass


class SafetyError(DeviceError):
    """Operación rechazada por condiciones de seguridad."""


class Observatory:
    DOME_TOLERANCE_DEG = 3.0
    STATUS_TTL_S = 1.0

    def __init__(self, cfg: Config, devices: Devices, bus: EventBus):
        from .sequencer import Sequencer  # evita ciclo de importación

        self.cfg, self.dev, self.bus = cfg, devices, bus
        self.safety = SafetyMonitor(cfg.safety)
        self.sequencer = Sequencer(self)
        self.dome_slaved = True
        self.sun_alt: Optional[float] = None

        self.camera_state = "idle"  # idle | exposing | reading
        self.exposure_progress = 0.0
        self.last_file: Optional[str] = None
        self.abort_exposure = threading.Event()
        self.camera_lock = threading.Lock()
        self._frame_seq = 0
        self._last_af_temp: Optional[float] = None
        self._emergency = threading.Lock()
        self._emergency_latched = False

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cache: Optional[tuple[float, dict]] = None

    # ------------------------------------------------------------ ciclo de vida
    def connect_all(self) -> dict[str, str]:
        result = {}
        for name in ("mount", "camera", "filterwheel", "focuser", "dome", "weather"):
            try:
                getattr(self.dev, name).connect()
                result[name] = "ok"
            except Exception as exc:
                result[name] = f"error: {exc}"
                self.bus.error("sistema", f"No se pudo conectar {name}: {exc}")
        self.bus.info("sistema", f"Conexión de equipos: {result}")
        return result

    def disconnect_all(self) -> None:
        for d in self.dev.all():
            try:
                d.disconnect()
            except Exception:
                pass

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._monitor_loop, name="monitor", daemon=True)
        self._thread.start()
        self.bus.info("sistema", "Monitor de seguridad iniciado")

    def stop(self) -> None:
        self._stop.set()
        self.sequencer.stop()
        if self._thread:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------ monitor / seguridad
    def _monitor_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # el monitor nunca debe morir
                self.bus.error("monitor", f"Error en el ciclo de monitoreo: {exc}")
            self._stop.wait(self.cfg.poll_interval_s)

    def tick(self) -> None:
        try:
            reading = self.dev.weather.read()
        except Exception:
            reading = None
        st = self.safety.evaluate(reading)
        try:
            self.sun_alt = astro.sun_altitude_deg(self.cfg.site)
        except Exception:
            pass
        if not st.safe:
            if not self._emergency_latched:
                self._emergency_latched = True
                self.bus.warning("seguridad", "Condiciones inseguras: " + "; ".join(st.reasons))
                if self._needs_closing():
                    threading.Thread(target=self.emergency_close, args=("; ".join(st.reasons),),
                                     name="emergency", daemon=True).start()
        elif self._emergency_latched:
            self._emergency_latched = False
            self.bus.info("seguridad", "Condiciones de nuevo seguras (la reapertura es manual)")
        self._sync_dome()

    def _needs_closing(self) -> bool:
        try:
            return self.dev.dome.shutter is not ShutterState.CLOSED or not self.dev.mount.at_park
        except Exception:
            return True  # fail-safe

    def emergency_close(self, reason: str = "manual") -> None:
        """Detiene todo, estaciona la montura y cierra el obturador. Idempotente."""
        if not self._emergency.acquire(blocking=False):
            return
        try:
            self.bus.error("seguridad", f"CIERRE DE EMERGENCIA: {reason}")
            self.sequencer.stop(wait=False)
            self.abort_exposure.set()
            errors = []
            try:
                self.dev.mount.abort_slew()
                if not self.dev.mount.at_park or self.dev.mount.slewing:
                    self.dev.mount.park()
            except Exception as exc:
                errors.append(f"montura: {exc}")
            deadline = time.monotonic() + 180
            try:
                while (self.dev.mount.slewing or not self.dev.mount.at_park) and time.monotonic() < deadline:
                    time.sleep(0.1)
                if self.dev.mount.slewing or not self.dev.mount.at_park:
                    errors.append("montura no confirmó estacionamiento")
            except Exception as exc:
                errors.append(f"montura: {exc}")
            try:
                self.dev.dome.close_shutter()
            except Exception as exc:
                errors.append(f"obturador: {exc}")
            if errors:
                self.bus.error("seguridad", "FALLOS EN EL CIERRE: " + "; ".join(errors) + " — requiere intervención humana")
            else:
                self.bus.info("seguridad", "Cierre completado")
        finally:
            self.abort_exposure.clear()
            self._emergency.release()

    def _sync_dome(self) -> None:
        if not self.dome_slaved:
            return
        try:
            m, d = self.dev.mount, self.dev.dome
            if m.at_park or d.shutter is not ShutterState.OPEN or d.slewing:
                return
            _, az = astro.altaz(m.ra_h, m.dec_deg, self.cfg.site)
            if abs((az - d.azimuth_deg + 180) % 360 - 180) > self.DOME_TOLERANCE_DEG:
                d.slew_to_azimuth(az)
        except Exception as exc:
            self.bus.warning("domo", f"Sincronización del domo falló: {exc}")

    def sync_dome_now(self) -> None:
        self._sync_dome()

    def _require_safe(self, what: str) -> None:
        if not self.safety.last.safe:
            raise SafetyError(f"{what} rechazado: " + "; ".join(self.safety.last.reasons))

    # ------------------------------------------------------------ apertura / montura / domo
    def open_shutter(self) -> None:
        st = self.safety.last
        if not st.can_open:
            why = "; ".join(st.reasons) or f"esperar {self.cfg.safety.safe_hold_minutes:g} min de condiciones seguras estables"
            raise SafetyError(f"Apertura rechazada: {why}")
        if self.cfg.safety.enforce_sun_limit and self.sun_alt is not None and \
                self.sun_alt > self.cfg.safety.sun_altitude_open_limit_deg:
            raise SafetyError(f"Apertura rechazada: Sol a {self.sun_alt:.1f}° (límite {self.cfg.safety.sun_altitude_open_limit_deg}°)")
        self.dev.dome.open_shutter()
        self.bus.info("domo", "Abriendo obturador")

    def close_shutter(self) -> None:
        self.dev.dome.close_shutter()
        self.bus.info("domo", "Cerrando obturador")

    def open_observatory(self) -> None:
        self.open_shutter()
        self.dev.mount.unpark()
        self.bus.info("montura", "Montura desestacionada")

    def close_observatory(self) -> None:
        self.sequencer.stop()
        self.dev.mount.abort_slew()
        self.dev.mount.park()
        self.bus.info("montura", "Estacionando montura")
        deadline = time.monotonic() + 180
        while self.dev.mount.slewing and time.monotonic() < deadline:
            time.sleep(0.1)
        self.close_shutter()

    def slew(self, ra_h: float, dec_deg: float, allow_closed: bool = False) -> None:
        self._require_safe("Apuntado")
        if not allow_closed and self.dev.dome.shutter is not ShutterState.OPEN:
            raise SafetyError("Apuntado rechazado: el obturador no está abierto")
        self.dev.mount.slew_to(ra_h, dec_deg)
        self.dev.mount.set_tracking(True)
        self.bus.info("montura", f"Apuntando a AR {ra_h:.4f} h, Dec {dec_deg:+.3f}°")

    def wait_slew(self, should_abort: Callable[[], bool], timeout: float = 300) -> None:
        deadline = time.monotonic() + timeout
        while self.dev.mount.slewing or self.dev.dome.slewing:
            if should_abort():
                raise DeviceError("Abortado durante el apuntado")
            if time.monotonic() > deadline:
                raise DeviceError("Timeout de apuntado")
            self._sync_dome()
            time.sleep(0.1)

    def wait_shutter(self, state: ShutterState, should_abort: Callable[[], bool], timeout: float = 300) -> None:
        deadline = time.monotonic() + timeout
        while self.dev.dome.shutter is not state:
            if should_abort():
                raise DeviceError("Abortado esperando al obturador")
            if time.monotonic() > deadline:
                raise DeviceError(f"Timeout esperando obturador {state.value}")
            time.sleep(0.1)

    # ------------------------------------------------------------ cámara
    def current_filter(self) -> str:
        try:
            names = self.dev.filterwheel.names
            return names[self.dev.filterwheel.position]
        except Exception:
            return ""

    def set_filter(self, name_or_pos: str | int) -> None:
        fw = self.dev.filterwheel
        pos = name_or_pos if isinstance(name_or_pos, int) else fw.names.index(name_or_pos)
        fw.set_position(pos)
        self.bus.info("filtros", f"Filtro {fw.names[pos]}")

    def take_frame(self, duration_s: float, image_type: str = "Light", object_name: str = "",
                   should_abort: Callable[[], bool] = lambda: False) -> Optional[Path]:
        """Exposición bloqueante + guardado FITS. Devuelve la ruta o None si se abortó."""
        d = self.dev
        with self.camera_lock:
            light = image_type in ("Light", "Flat")
            started = datetime.now(timezone.utc)
            self.camera_state, self.exposure_progress = "exposing", 0.0

            def progress(f: float) -> None:
                self.exposure_progress = f

            try:
                data = d.camera.expose(duration_s, light, lambda: should_abort() or self.abort_exposure.is_set(), progress)
                if data is None:
                    self.bus.warning("camara", "Exposición abortada")
                    return None
                self.camera_state = "reading"
                info = FrameInfo(image_type=image_type, object_name=object_name, exposure_s=duration_s,
                                 filter_name=self.current_filter() if light else "",
                                 ccd_temp_c=self._safe(lambda: d.camera.ccd_temperature_c),
                                 binning=self._safe(lambda: d.camera.binning, 1),
                                 focus_pos=self._safe(lambda: d.focuser.position), date_obs=started)
                if not d.mount.at_park and light:
                    info.ra_h, info.dec_deg = self._safe(lambda: d.mount.ra_h), self._safe(lambda: d.mount.dec_deg)
                    if info.ra_h is not None and info.dec_deg is not None:
                        info.airmass = airmass(astro.altaz(info.ra_h, info.dec_deg, self.cfg.site, started)[0])
                self._frame_seq += 1
                path = save_frame(data, info, self.cfg.site, self.cfg.data_path, self._frame_seq)
                self.last_file = str(path)
                self.bus.info("camara", f"Guardado {path.name}")
                return path
            finally:
                self.camera_state, self.exposure_progress = "idle", 0.0

    @staticmethod
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    def start_exposure_async(self, duration_s: float, image_type: str = "Light", object_name: str = "") -> None:
        if self.sequencer.running:
            raise DeviceError("Hay una secuencia en ejecución")
        if self.camera_lock.locked():
            raise DeviceError("La cámara está ocupada")
        if image_type in ("Light", "Flat"):
            self._require_safe("Exposición")

        def run() -> None:
            try:
                self.take_frame(duration_s, image_type, object_name)
            except Exception as exc:
                self.bus.error("camara", f"Exposición falló: {exc}")

        threading.Thread(target=run, name="exposure", daemon=True).start()

    def abort_current_exposure(self) -> None:
        self.abort_exposure.set()
        threading.Timer(1.0, self.abort_exposure.clear).start()

    def run_autofocus(self, should_abort: Callable[[], bool] = lambda: False, **kw) -> int:
        with self.camera_lock:
            best = autofocus(self.dev.camera, self.dev.focuser, should_abort=should_abort,
                             log=lambda m: self.bus.info("enfoque", m), **kw)
        self._last_af_temp = self._safe(lambda: self.dev.focuser.temperature_c)
        return best

    def needs_refocus(self) -> bool:
        t = self._safe(lambda: self.dev.focuser.temperature_c)
        if t is None or self._last_af_temp is None:
            return self._last_af_temp is None
        return abs(t - self._last_af_temp) > self.cfg.autofocus_temp_delta_c

    # ------------------------------------------------------------ estado
    def invalidate_status(self) -> None:
        self._cache = None

    def status(self, fresh: bool = False) -> dict:
        now = time.monotonic()
        if not fresh and self._cache and now - self._cache[0] < self.STATUS_TTL_S:
            return self._cache[1]
        d = self.dev
        g = self._safe

        def part(fn):
            try:
                return fn()
            except Exception as exc:
                return {"error": str(exc)}

        st = self.safety.last
        s = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "site": self.cfg.site.name,
            "sun_altitude_deg": self.sun_alt,
            "mount": part(lambda: dict(connected=d.mount.connected, ra_h=d.mount.ra_h, dec_deg=d.mount.dec_deg,
                                       slewing=d.mount.slewing, tracking=d.mount.tracking, parked=d.mount.at_park)),
            "camera": part(lambda: dict(connected=d.camera.connected, state=self.camera_state,
                                        progress=self.exposure_progress, temperature_c=d.camera.ccd_temperature_c,
                                        cooler_on=d.camera.cooler_on, binning=d.camera.binning,
                                        last_file=self.last_file)),
            "filterwheel": part(lambda: dict(connected=d.filterwheel.connected, names=d.filterwheel.names,
                                             position=d.filterwheel.position, current=self.current_filter())),
            "focuser": part(lambda: dict(connected=d.focuser.connected, position=d.focuser.position,
                                         moving=d.focuser.moving, temperature_c=d.focuser.temperature_c)),
            "dome": part(lambda: dict(connected=d.dome.connected, shutter=d.dome.shutter.value,
                                      azimuth_deg=d.dome.azimuth_deg, slewing=d.dome.slewing, slaved=self.dome_slaved)),
            "weather": part(lambda: (st.reading.__dict__ if st.reading else None)),
            "safety": dict(safe=st.safe, can_open=st.can_open, reasons=st.reasons),
            "sequence": self.sequencer.status(),
        }
        self._cache = (now, s)
        return s
