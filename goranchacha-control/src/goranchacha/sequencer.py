"""Ejecución automática de secuencias de observación."""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Optional

from . import astro
from .devices.base import DeviceError, ShutterState
from .scheduler import SequenceOptions, Target, next_target

if TYPE_CHECKING:
    from .observatory import Observatory


class _Aborted(Exception):
    pass


class Sequencer:
    def __init__(self, obs: "Observatory"):
        self.obs = obs
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._state = "idle"  # idle|waiting_dark|opening|focusing|waiting_target|running|done|stopped|error
        self._message = ""
        self._current: Optional[str] = None
        self._done = 0
        self._total = 0
        self._pending: list[str] = []

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict:
        return dict(state=self._state, message=self._message, target=self._current,
                    frames_done=self._done, frames_total=self._total, pending=list(self._pending))

    def start(self, targets: list[Target], options: SequenceOptions | None = None) -> None:
        if self.running:
            raise DeviceError("Ya hay una secuencia en ejecución")
        if not targets:
            raise DeviceError("La secuencia no tiene objetivos")
        if self.obs.camera_lock.locked():
            raise DeviceError("La cámara está ocupada")
        self._stop.clear()
        self._done = 0
        self._total = sum(e.count for t in targets for e in t.exposures)
        self._pending = [t.name for t in targets]
        self._state, self._message, self._current = "running", "", None
        self._thread = threading.Thread(target=self._run, args=(list(targets), options or SequenceOptions()),
                                        name="sequencer", daemon=True)
        self._thread.start()

    def stop(self, wait: bool = True) -> None:
        self._stop.set()
        if wait and self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=30)

    # ------------------------------------------------------------ internos
    def _check(self) -> None:
        if self._stop.is_set():
            raise _Aborted("Detenida por el usuario")
        if not self.obs.safety.last.safe:
            raise _Aborted("Condiciones inseguras: " + "; ".join(self.obs.safety.last.reasons))

    def _sleep(self, s: float) -> None:
        end = time.monotonic() + s
        while time.monotonic() < end:
            self._check()
            time.sleep(min(0.2, max(end - time.monotonic(), 0)))

    def _run(self, targets: list[Target], opt: SequenceOptions) -> None:
        o, bus = self.obs, self.obs.bus
        bus.info("secuencia", f"Inicio: {len(targets)} objetivos, {self._total} imágenes")
        try:
            needs_sky = any(t.ra_h is not None for t in targets)
            if needs_sky and opt.require_dark:
                self._state = "waiting_dark"
                while True:
                    self._check()
                    alt = astro.sun_altitude_deg(o.cfg.site)
                    self._message = f"Sol a {alt:.1f}°, esperando < {opt.sun_altitude_limit_deg}°"
                    if alt < opt.sun_altitude_limit_deg:
                        break
                    self._sleep(15)
            if needs_sky and o.dev.dome.shutter is not ShutterState.OPEN:
                if not opt.auto_open:
                    raise _Aborted("El observatorio está cerrado y auto_open está desactivado")
                self._state, self._message = "opening", "Abriendo observatorio"
                o.open_observatory()
                o.wait_shutter(ShutterState.OPEN, lambda: self._stop.is_set() or not o.safety.last.safe)
            elif needs_sky and o.dev.mount.at_park:
                o.dev.mount.unpark()
            if needs_sky and opt.autofocus_at_start:
                self._state, self._message = "focusing", "Autoenfoque inicial"
                o.run_autofocus(lambda: self._stop.is_set())

            pending = list(targets)
            while pending:
                self._check()
                tgt = next_target(pending, o.cfg.site)
                if tgt is None:
                    self._state, self._message = "waiting_target", "Ningún objetivo observable ahora"
                    self._sleep(10)
                    continue
                self._state, self._message, self._current = "running", "", tgt.name
                self._observe(tgt, opt)
                pending.remove(tgt)
                self._pending = [t.name for t in pending]
            self._current = None
            if opt.close_when_done and needs_sky:
                o.close_observatory()
                o.wait_shutter(ShutterState.CLOSED, lambda: False)  # "completada" = observatorio cerrado
            self._state, self._message = "done", "Secuencia completada"
            bus.info("secuencia", "Secuencia completada")
        except _Aborted as exc:
            self._state, self._message = "stopped", str(exc)
            bus.warning("secuencia", f"Secuencia detenida: {exc}")
        except Exception as exc:
            self._state, self._message = "error", str(exc)
            bus.error("secuencia", f"Secuencia con error: {exc}")
        finally:
            self._current = None

    def _observe(self, tgt: Target, opt: SequenceOptions) -> None:
        o = self.obs
        o.bus.info("secuencia", f"Objetivo {tgt.name}")
        if tgt.ra_h is not None:
            o.slew(tgt.ra_h, tgt.dec_deg)
            o.wait_slew(lambda: self._stop.is_set() or not o.safety.last.safe)
        for spec in tgt.exposures:
            o.dev.camera.set_binning(spec.binning)
            if spec.filter and spec.image_type in ("Light", "Flat"):
                o.set_filter(spec.filter)
            for i in range(spec.count):
                self._check()
                if spec.image_type == "Light" and tgt.ra_h is not None and o.needs_refocus():
                    self._state = "focusing"
                    o.run_autofocus(lambda: self._stop.is_set())
                    self._state = "running"
                path = o.take_frame(spec.exposure_s, spec.image_type, tgt.name, lambda: self._stop.is_set())
                if path is None:
                    self._check()
                    raise DeviceError("Exposición abortada")
                self._done += 1
