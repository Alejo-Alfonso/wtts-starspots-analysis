"""Arranque del servidor del observatorio:  goranchacha-server --config config.yaml"""
from __future__ import annotations

import argparse
import ipaddress

import uvicorn

from ..auth import TokenSigner, UserStore
from ..config import load_config
from ..devices.factory import build_devices
from ..logbook import EventBus, Logbook
from ..observatory import Observatory
from .app import create_app


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--insecure", action="store_true", help="permitir acceso de red SIN TLS (no recomendado)")
    a = ap.parse_args()
    cfg = load_config(a.config)
    s = cfg.server
    if not _is_loopback(s.host) and not (s.ssl_certfile and s.ssl_keyfile) and not a.insecure:
        raise SystemExit("Acceso remoto sin TLS rechazado: configure server.ssl_certfile/ssl_keyfile "
                         "(o use un túnel VPN/proxy con TLS y --insecure)")
    data = cfg.data_path
    users = UserStore(data / "usuarios.db")
    if users.count() == 0:
        raise SystemExit("No hay usuarios. Cree uno con:  goranchacha-user ADMIN admin"
                         + (f" --config {a.config}" if a.config else ""))
    bus = EventBus(Logbook(data / "bitacora.db"))
    obs = Observatory(cfg, build_devices(cfg), bus)
    obs.connect_all()
    obs.start()
    app = create_app(obs, users, TokenSigner.from_file(data / "secreto.key", s.token_ttl_minutes * 60))
    try:
        uvicorn.run(app, host=s.host, port=s.port, ssl_certfile=s.ssl_certfile, ssl_keyfile=s.ssl_keyfile)
    finally:
        obs.stop()
        obs.disconnect_all()


if __name__ == "__main__":
    main()
