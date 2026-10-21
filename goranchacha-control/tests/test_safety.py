import time

from goranchacha.config import SafetyConfig
from goranchacha.devices.base import WeatherReading
from goranchacha.safety import SafetyMonitor


def good(**kw):
    base = dict(temperature_c=12, humidity_pct=50, wind_speed_ms=3, wind_gust_ms=5, dew_point_c=3,
                cloud_cover_pct=10, rain_rate_mm_h=0, timestamp=time.time())
    base.update(kw)
    return WeatherReading(**base)


def test_safe_and_hold():
    m = SafetyMonitor(SafetyConfig(safe_hold_minutes=10))
    t0 = time.time()
    s = m.evaluate(good(timestamp=t0), now=t0)
    assert s.safe and not s.can_open
    s = m.evaluate(good(timestamp=t0 + 601), now=t0 + 601)
    assert s.can_open


def test_each_limit_trips():
    m = SafetyMonitor(SafetyConfig(safe_hold_minutes=0))
    for kw in (dict(rain_rate_mm_h=0.2), dict(wind_speed_ms=20), dict(wind_gust_ms=30),
               dict(humidity_pct=95), dict(dew_point_c=11), dict(cloud_cover_pct=90)):
        assert not m.evaluate(good(**kw)).safe, kw


def test_stale_reading_and_sensor_failure_are_unsafe():
    m = SafetyMonitor(SafetyConfig(safe_hold_minutes=0, max_consecutive_failures=3))
    assert not m.evaluate(good(timestamp=time.time() - 1000)).safe
    m.evaluate(good())
    assert m.evaluate(None).safe  # fallo transitorio, se conserva
    m.evaluate(None)
    s = m.evaluate(None)
    assert not s.safe and "sin respuesta" in s.reasons[0]


def test_no_reading_ever_is_unsafe():
    assert not SafetyMonitor(SafetyConfig()).evaluate(None).safe
