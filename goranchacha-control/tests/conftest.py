import pytest

from goranchacha.config import Config
from goranchacha.devices.factory import build_devices
from goranchacha.logbook import EventBus, Logbook
from goranchacha.observatory import Observatory


@pytest.fixture
def cfg(tmp_path):
    c = Config(data_dir=str(tmp_path / "datos"), poll_interval_s=0.1)
    c.devices.time_scale = 2000.0
    c.safety.safe_hold_minutes = 0
    c.safety.enforce_sun_limit = False  # las pruebas corren a cualquier hora
    return c


@pytest.fixture
def obs(cfg, tmp_path):
    bus = EventBus(Logbook(tmp_path / "log.db"))
    o = Observatory(cfg, build_devices(cfg), bus)
    o.connect_all()
    o.tick()  # primera lectura meteorológica
    yield o
    o.stop()
