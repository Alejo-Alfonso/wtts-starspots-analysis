"""Utilidades astronómicas (alt/az, Sol) con astropy, sin acceso a red."""
from __future__ import annotations

from datetime import datetime, timezone

import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.time import Time
from astropy.utils import iers

iers.conf.auto_download = False  # el observatorio no debe depender de internet
iers.conf.iers_degraded_accuracy = "ignore"

from .config import SiteConfig


def location(site: SiteConfig) -> EarthLocation:
    return EarthLocation(
        lat=site.latitude_deg * u.deg, lon=site.longitude_deg * u.deg, height=site.elevation_m * u.m
    )


def _time(when: datetime | None) -> Time:
    return Time(when or datetime.now(timezone.utc))


def altaz(ra_h: float, dec_deg: float, site: SiteConfig, when: datetime | None = None) -> tuple[float, float]:
    t = _time(when)
    c = SkyCoord(ra=ra_h * u.hourangle, dec=dec_deg * u.deg).transform_to(
        AltAz(obstime=t, location=location(site))
    )
    return float(c.alt.deg), float(c.az.deg)


def sun_altitude_deg(site: SiteConfig, when: datetime | None = None) -> float:
    t = _time(when)
    sun = get_body("sun", t, location(site)).transform_to(AltAz(obstime=t, location=location(site)))
    return float(sun.alt.deg)
