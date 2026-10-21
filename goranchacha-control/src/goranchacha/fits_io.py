"""Escritura de imágenes FITS con cabeceras científicas estándar."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from astropy.io import fits

from . import __version__
from .config import SiteConfig


@dataclass
class FrameInfo:
    image_type: str = "Light"  # Light | Dark | Bias | Flat
    object_name: str = ""
    exposure_s: float = 0.0
    filter_name: str = ""
    ra_h: Optional[float] = None
    dec_deg: Optional[float] = None
    ccd_temp_c: Optional[float] = None
    binning: int = 1
    focus_pos: Optional[int] = None
    airmass: Optional[float] = None
    date_obs: Optional[datetime] = None  # inicio de la exposición (UTC)


def night_folder(when: datetime) -> str:
    """Carpeta por noche: la fecha local-civil de inicio de la noche (UTC-5, Colombia)."""
    local = when.astimezone(timezone(timedelta(hours=-5)))
    return (local - timedelta(hours=12)).strftime("%Y-%m-%d")


def _ascii(s: str) -> str:
    """FITS solo admite ASCII imprimible en cabeceras: quita tildes y símbolos no ASCII."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", s).strip("_") or "frame"


def save_frame(data: np.ndarray, info: FrameInfo, site: SiteConfig, root: Path, seq: int) -> Path:
    when = info.date_obs or datetime.now(timezone.utc)
    folder = Path(root) / night_folder(when)
    folder.mkdir(parents=True, exist_ok=True)
    stem = info.object_name if info.image_type == "Light" and info.object_name else info.image_type
    parts = [_safe(stem)]
    if info.filter_name and info.image_type in ("Light", "Flat"):
        parts.append(_safe(info.filter_name))
    parts += [when.strftime("%Y%m%dT%H%M%S"), f"{info.exposure_s:g}s", f"{seq:04d}"]
    path = folder / ("_".join(parts) + ".fits")

    hdu = fits.PrimaryHDU(data.astype(np.uint16))
    h = hdu.header
    h["DATE-OBS"] = (when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], "UTC, inicio de exposicion")
    h["EXPTIME"] = (info.exposure_s, "[s] tiempo de exposicion")
    h["IMAGETYP"] = (_ascii(info.image_type), "tipo de imagen")
    h["OBJECT"] = (_ascii(info.object_name), "objeto")
    h["FILTER"] = (_ascii(info.filter_name), "filtro")
    if info.ra_h is not None and info.dec_deg is not None:
        h["RA"] = (round(info.ra_h * 15, 6), "[deg] AR del puntero")
        h["DEC"] = (round(info.dec_deg, 6), "[deg] Dec del puntero")
    if info.ccd_temp_c is not None:
        h["CCD-TEMP"] = (info.ccd_temp_c, "[C] temperatura del sensor")
    h["XBINNING"] = info.binning
    h["YBINNING"] = info.binning
    if info.focus_pos is not None:
        h["FOCUSPOS"] = (info.focus_pos, "posicion del enfocador")
    if info.airmass is not None:
        h["AIRMASS"] = (round(info.airmass, 3), "masa de aire")
    h["OBSERVAT"] = _ascii(site.name)
    h["TELESCOP"] = _ascii(site.telescope)
    h["INSTRUME"] = _ascii(site.instrument)
    h["OBSERVER"] = _ascii(site.observer)
    h["SITELAT"] = (site.latitude_deg, "[deg N]")
    h["SITELONG"] = (site.longitude_deg, "[deg E]")
    h["SITEELEV"] = (site.elevation_m, "[m]")
    h["SWCREATE"] = f"goranchacha-control {__version__}"
    hdu.writeto(path, overwrite=False)
    return path
