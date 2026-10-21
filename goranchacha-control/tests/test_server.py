import time

import pytest
from fastapi.testclient import TestClient

from goranchacha.auth import TokenSigner, UserStore
from goranchacha.client.api import ApiError, ObservatoryClient
from goranchacha.server.app import create_app


@pytest.fixture
def api(obs, tmp_path):
    users = UserStore(tmp_path / "u.db")
    users.add("ana", "contrasena-larga-1", "viewer")
    users.add("luis", "contrasena-larga-2", "operator")
    users.add("root", "contrasena-larga-3", "admin")
    app = create_app(obs, users, TokenSigner(b"k" * 32, 3600))
    http = TestClient(app, base_url="http://testserver")
    c = ObservatoryClient("http://testserver", client=http)
    return c, http, users


def test_requires_auth(api):
    _, http, _ = api
    assert http.get("/status").status_code == 401
    assert http.get("/status", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_roles(api):
    c, http, _ = api
    c.login("ana", "contrasena-larga-1")
    assert c.status()["site"].startswith("Observatorio")
    with pytest.raises(ApiError) as e:
        c.slew(5, 5)
    assert e.value.status == 403
    with pytest.raises(ApiError) as e:
        c.emergency_close()
    assert e.value.status == 403


def test_bad_login_and_lockout(api):
    c, _, _ = api
    for _ in range(5):
        with pytest.raises(ApiError):
            c.login("luis", "mala")
    with pytest.raises(ApiError):
        c.login("luis", "contrasena-larga-2")  # bloqueado temporalmente


def test_expired_and_tampered_token():
    s = TokenSigner(b"k" * 32, -1)
    assert s.verify(s.issue("a", "admin")) is None
    s = TokenSigner(b"k" * 32, 60)
    t = s.issue("a", "viewer")
    body, sig = t.rsplit(".", 1)
    assert s.verify(body + "." + "0" * 64) is None
    import base64, json
    forged = base64.urlsafe_b64encode(json.dumps({"sub": "a", "role": "admin", "exp": time.time() + 99}).encode()).decode()
    assert s.verify(forged + "." + sig) is None


def test_operator_flow(api, obs):
    c, _, _ = api
    c.login("luis", "contrasena-larga-2")
    with pytest.raises(ApiError) as e:
        c.slew(5, 10)  # obturador cerrado
    assert e.value.status == 409
    c.open_observatory()
    end = time.time() + 10
    while obs.status(fresh=True)["dome"]["shutter"] != "open" and time.time() < end:
        time.sleep(0.05)
    c.slew(5, 10)
    c.set_filter("V")
    c.expose(1, "Light", "t")
    end = time.time() + 10
    while not obs.last_file and time.time() < end:
        time.sleep(0.05)
    assert obs.last_file
    assert c.status()["filterwheel"]["current"] == "V"
    c.emergency_close()
    end = time.time() + 15
    while obs.status(fresh=True)["dome"]["shutter"] != "closed" and time.time() < end:
        time.sleep(0.05)
    assert obs.status(fresh=True)["mount"]["parked"]
    assert any("usuario" == r["source"] for r in c.logbook())


def test_input_validation(api):
    c, _, _ = api
    c.login("luis", "contrasena-larga-2")
    with pytest.raises(ApiError) as e:
        c.slew(30, 5)
    assert e.value.status == 422
    with pytest.raises(ApiError) as e:
        c.expose(1, "Bogus")
    assert e.value.status == 422


def test_user_password_policy(tmp_path):
    with pytest.raises(ValueError):
        UserStore(tmp_path / "x.db").add("a", "corta", "admin")
