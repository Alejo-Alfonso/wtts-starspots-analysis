import httpx
import pytest

from goranchacha.devices.alpaca import AlpacaDome, AlpacaMount, AlpacaWeather
from goranchacha.devices.base import DeviceError, ShutterState


def make(cls, handler):
    return cls("http://x:11111", 0, client=httpx.Client(transport=httpx.MockTransport(handler)))


def ok(value=None, err=0, msg=""):
    return httpx.Response(200, json={"Value": value, "ErrorNumber": err, "ErrorMessage": msg})


def test_mount_get_put_paths():
    seen = []

    def h(req):
        seen.append((req.method, req.url.path, req.content.decode()))
        return ok(5.5)

    m = make(AlpacaMount, h)
    assert m.ra_h == 5.5
    m.slew_to(1.0, 2.0)
    assert seen[0][:2] == ("GET", "/api/v1/telescope/0/rightascension")
    assert seen[1][:2] == ("PUT", "/api/v1/telescope/0/slewtocoordinatesasync")
    assert "RightAscension=1.0" in seen[1][2] and "Declination=2.0" in seen[1][2]


def test_alpaca_error_and_http_failure():
    with pytest.raises(DeviceError, match="1035"):
        make(AlpacaMount, lambda r: ok(err=1035, msg="parked")).slew_to(1, 1)

    def boom(req):
        raise httpx.ConnectError("sin red")

    with pytest.raises(DeviceError):
        _ = make(AlpacaMount, boom).ra_h


def test_dome_shutter_mapping():
    assert make(AlpacaDome, lambda r: ok(0)).shutter is ShutterState.OPEN
    assert make(AlpacaDome, lambda r: ok(1)).shutter is ShutterState.CLOSED
    assert make(AlpacaDome, lambda r: ok(4)).shutter is ShutterState.ERROR


def test_weather_tolerates_missing_properties():
    def h(req):
        return ok(err=1024, msg="no impl") if req.url.path.endswith("cloudcover") else ok(3.0)

    r = make(AlpacaWeather, h).read()
    assert r.cloud_cover_pct is None and r.wind_speed_ms == 3.0
