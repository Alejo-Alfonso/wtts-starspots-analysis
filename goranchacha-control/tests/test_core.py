import time
from datetime import datetime, timezone

import numpy as np
import pytest
from astropy.io import fits

from goranchacha.autofocus import measure_hfr
from goranchacha.devices.base import DeviceError, ShutterState
from goranchacha.devices.simulators import SimWorld
from goranchacha.observatory import SafetyError
from goranchacha.scheduler import ExposureSpec, SequenceOptions, Target, next_target


def wait(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_autofocus_finds_best_position(obs):
    obs.dev.mount.unpark()
    best = obs.run_autofocus(step=150)
    assert abs(best - SimWorld.BEST_FOCUS) < 150
    assert measure_hfr(obs.dev.camera.expose(2)) < 2.5


def test_open_slew_and_expose_writes_fits(obs, cfg):
    with pytest.raises(SafetyError):
        obs.slew(5.0, 10.0)  # obturador cerrado
    obs.open_observatory()
    assert wait(lambda: obs.dev.dome.shutter is ShutterState.OPEN)
    obs.slew(5.0, 10.0)
    obs.wait_slew(lambda: False)
    p = obs.take_frame(5, "Light", "TEST OBJ")
    h = fits.getheader(p)
    assert h["OBJECT"] == "TEST OBJ" and h["EXPTIME"] == 5 and h["XBINNING"] == 1
    assert h["OBSERVAT"].startswith("Observatorio Astron") and abs(h["RA"] - 75) < 1e-6
    assert p.parent.parent == cfg.data_path


def test_bias_and_dark_have_no_pointing(obs):
    p = obs.take_frame(10, "Dark")
    h = fits.getheader(p)
    assert h["IMAGETYP"] == "Dark" and "RA" not in h


def test_rain_triggers_emergency_close(obs):
    obs.open_observatory()
    wait(lambda: obs.dev.dome.shutter is ShutterState.OPEN)
    obs.slew(5.0, 10.0)
    obs.dev.weather.set(rain_rate_mm_h=1.0)
    obs.tick()
    assert wait(lambda: obs.dev.dome.shutter is ShutterState.CLOSED, 15)
    assert obs.dev.mount.at_park
    with pytest.raises(SafetyError):
        obs.open_observatory()


def test_weather_sensor_failure_closes(obs):
    obs.open_observatory()
    wait(lambda: obs.dev.dome.shutter is ShutterState.OPEN)
    obs.dev.weather.fail = True
    for _ in range(3):
        obs.tick()
    assert wait(lambda: obs.dev.dome.shutter is ShutterState.CLOSED, 15)


def test_dome_follows_mount(obs):
    obs.open_observatory()
    wait(lambda: obs.dev.dome.shutter is ShutterState.OPEN)
    obs.slew(8.0, 20.0, )
    obs.wait_slew(lambda: False)
    obs.sync_dome_now()
    assert wait(lambda: not obs.dev.dome.slewing)
    from goranchacha import astro
    _, az = astro.altaz(8.0, 20.0, obs.cfg.site)
    assert abs((obs.dev.dome.azimuth_deg - az + 180) % 360 - 180) < 6


def test_sequence_runs_and_closes(obs):
    seq = [Target(name="WASP-12", ra_h=6.5, dec_deg=29.7, min_altitude_deg=-90,
                  exposures=[ExposureSpec(filter="R", exposure_s=2, count=3),
                             ExposureSpec(filter="V", exposure_s=2, count=2)]),
           Target(name="Calib", exposures=[ExposureSpec(image_type="Bias", exposure_s=0, count=2)], priority=1)]
    obs.sequencer.start(seq, SequenceOptions(require_dark=False))
    assert wait(lambda: obs.sequencer.status()["state"] in ("done", "error", "stopped"), 60)
    st = obs.sequencer.status()
    assert st["state"] == "done", st
    assert st["frames_done"] == 7
    assert len(list(obs.cfg.data_path.rglob("*.fits"))) == 7
    assert obs.dev.dome.shutter is ShutterState.CLOSED and obs.dev.mount.at_park


def test_sequence_aborts_on_weather(obs):
    seq = [Target(name="X", ra_h=6.5, dec_deg=29.7, min_altitude_deg=-90,
                  exposures=[ExposureSpec(filter="R", exposure_s=600, count=50)])]
    obs.sequencer.start(seq, SequenceOptions(require_dark=False, autofocus_at_start=False))
    assert wait(lambda: obs.camera_state == "exposing", 30)
    obs.dev.weather.set(wind_speed_ms=30)
    obs.tick()
    assert wait(lambda: obs.sequencer.status()["state"] == "stopped", 30)
    assert wait(lambda: obs.dev.dome.shutter is ShutterState.CLOSED, 30)


def test_next_target_priority_and_altitude(cfg):
    site = cfg.site
    now = datetime(2026, 3, 20, 3, 0, tzinfo=timezone.utc)  # 22:00 hora local, LST ~10 h
    up = Target(name="up", ra_h=10.0, dec_deg=5.0, exposures=[ExposureSpec(exposure_s=1)], priority=3)
    hi = Target(name="hi", ra_h=10.0, dec_deg=5.0, exposures=[ExposureSpec(exposure_s=1)], priority=8)
    down = Target(name="down", ra_h=17.0, dec_deg=-80.0, exposures=[ExposureSpec(exposure_s=1)], priority=10)
    assert next_target([up, hi, down], site, now).name == "hi"
    assert next_target([down], site, now) is None


def test_validation():
    with pytest.raises(Exception):
        Target(name="x", ra_h=30, dec_deg=0, exposures=[ExposureSpec(exposure_s=1)])
    with pytest.raises(Exception):
        Target(name="x", ra_h=1, exposures=[ExposureSpec(exposure_s=1)])
