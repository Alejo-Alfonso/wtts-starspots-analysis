"""Autoenfoque por barrido V-curve: ajuste parabólico de HFR² frente a posición."""
from __future__ import annotations

import time
from typing import Callable

import numpy as np

from .devices.base import Camera, DeviceError, Focuser


def measure_hfr(img: np.ndarray, box: int = 20) -> float:
    """HFR (radio de media luz, px) de la estrella más brillante. Devuelve nan si no hay estrella."""
    a = img.astype(float)
    bg = np.median(a)
    a = a - bg
    noise = 1.4826 * np.median(np.abs(a)) + 1e-9
    y, x = np.unravel_index(np.argmax(a), a.shape)
    if a[y, x] < 8 * noise:
        return float("nan")
    y0, y1, x0, x1 = max(y - box, 0), min(y + box + 1, a.shape[0]), max(x - box, 0), min(x + box + 1, a.shape[1])
    cut = np.clip(a[y0:y1, x0:x1], 0, None)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    r = np.hypot(yy - y, xx - x).ravel()
    f = cut.ravel()
    order = np.argsort(r)
    cum = np.cumsum(f[order])
    if cum[-1] <= 0:
        return float("nan")
    return float(r[order][np.searchsorted(cum, cum[-1] / 2)])


def autofocus(
    camera: Camera,
    focuser: Focuser,
    exposure_s: float = 3.0,
    step: int = 150,
    n_points: int = 7,
    should_abort: Callable[[], bool] = lambda: False,
    log: Callable[[str], None] = lambda m: None,
    max_rounds: int = 3,
) -> int:
    """Devuelve la mejor posición (y deja el enfocador en ella). Lanza DeviceError si falla."""

    def go(pos: int) -> None:
        focuser.move_to(pos)
        while focuser.moving:
            if should_abort():
                raise DeviceError("Autoenfoque abortado")
            time.sleep(0.05)

    origin = focuser.position
    center = origin
    for round_ in range(1, max_rounds + 1):
        positions = [center + (i - n_points // 2) * step for i in range(n_points)]
        positions = [p for p in positions if 0 <= p <= focuser.max_step]
        pts: list[tuple[int, float]] = []
        for p in positions:
            go(p)
            img = camera.expose(exposure_s, True, should_abort)
            if img is None:
                raise DeviceError("Autoenfoque abortado")
            hfr = measure_hfr(img)
            log(f"Autoenfoque (ronda {round_}): pos {p} HFR {hfr:.2f}")
            if np.isfinite(hfr):
                pts.append((p, hfr))
        if len(pts) < 4:
            go(origin)
            raise DeviceError("Autoenfoque: estrellas insuficientes")
        x = np.array([p for p, _ in pts], float)
        y = np.array([h * h for _, h in pts])
        a, b, _c = np.polyfit(x, y, 2)
        best = -b / (2 * a) if a > 0 else float("nan")
        span = x.max() - x.min()
        if np.isfinite(best) and x.min() <= best <= x.max():
            best = int(round(best))
            go(best)
            log(f"Autoenfoque: mejor posición {best}")
            return best
        if np.isfinite(best) and abs(best - center) <= 2 * span and 0 <= best <= focuser.max_step:
            center = int(round(best))  # el mínimo está cerca pero fuera: recentrar y repetir
            log(f"Autoenfoque: recentrando en {center}")
            continue
        break
    go(origin)
    raise DeviceError("Autoenfoque: no se encontró un mínimo fiable; revisar el foco manualmente")
