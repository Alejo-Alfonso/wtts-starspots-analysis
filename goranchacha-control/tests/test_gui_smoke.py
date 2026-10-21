"""Humo de la GUI en modo offscreen contra un servidor real en un hilo."""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import uvicorn

from goranchacha.auth import TokenSigner, UserStore
from goranchacha.client.api import ObservatoryClient
from goranchacha.server.app import create_app


@pytest.fixture
def server(obs, tmp_path):
    users = UserStore(tmp_path / "u.db")
    users.add("luis", "contrasena-larga-2", "operator")
    users.add("ana", "contrasena-larga-1", "viewer")
    cfg = uvicorn.Config(create_app(obs, users, TokenSigner(b"k" * 32, 3600)), host="127.0.0.1", port=0, log_level="error")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    while not srv.started:
        time.sleep(0.02)
    port = srv.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)


def _pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def test_gui_renders_and_respects_role(server):
    from PySide6.QtWidgets import QApplication
    from goranchacha.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    c = ObservatoryClient(server)
    c.login("ana", "contrasena-larga-1")
    w = MainWindow(c)
    _pump(app, 1.5)
    assert "SEGURAS" in w.banner.text()
    assert w.lbl["Obturador"].text() == "closed"
    assert not w.emergency.isEnabled()  # viewer
    w.timer.stop()

    c2 = ObservatoryClient(server)
    c2.login("luis", "contrasena-larga-2")
    w2 = MainWindow(c2)
    assert w2.emergency.isEnabled()
    targets, opts = w2._plan_args()
    assert targets[0]["name"] == "Objetivo 1" and opts["require_dark"] is True
    w2.timer.stop()
