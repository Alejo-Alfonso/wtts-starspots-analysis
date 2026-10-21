"""Cliente HTTP del servidor del observatorio (usado por la GUI y por scripts)."""
from __future__ import annotations

from typing import Any, Optional

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status


class ObservatoryClient:
    def __init__(self, base_url: str, verify: bool | str = True, timeout: float = 15.0,
                 client: Optional[httpx.Client] = None):
        self._http = client or httpx.Client(base_url=base_url.rstrip("/"), verify=verify, timeout=timeout)
        self.token: Optional[str] = None
        self.role: Optional[str] = None

    def _req(self, method: str, path: str, json: Any = None, params: dict | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = self._http.request(method, path, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ApiError(0, f"Sin conexión con el observatorio: {exc}") from exc
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, str(detail))
        return r.json()

    def login(self, username: str, password: str) -> str:
        d = self._req("POST", "/auth/login", {"username": username, "password": password})
        self.token, self.role = d["token"], d["role"]
        return self.role

    def status(self) -> dict: return self._req("GET", "/status")
    def logbook(self, limit: int = 200) -> list: return self._req("GET", "/logbook", params={"limit": limit})
    def sequence(self) -> dict: return self._req("GET", "/sequence")
    def emergency_close(self): return self._req("POST", "/emergency/close")
    def open_observatory(self): return self._req("POST", "/observatory/open")
    def close_observatory(self): return self._req("POST", "/observatory/close")
    def slew(self, ra_h: float, dec_deg: float): return self._req("POST", "/mount/slew", {"ra_h": ra_h, "dec_deg": dec_deg})
    def abort_slew(self): return self._req("POST", "/mount/abort")
    def park(self): return self._req("POST", "/mount/park")
    def unpark(self): return self._req("POST", "/mount/unpark")
    def tracking(self, on: bool): return self._req("POST", "/mount/tracking", {"on": on})
    def expose(self, duration_s: float, image_type: str = "Light", object_name: str = ""):
        return self._req("POST", "/camera/expose", {"duration_s": duration_s, "image_type": image_type, "object_name": object_name})
    def abort_exposure(self): return self._req("POST", "/camera/abort")
    def cooler(self, on: bool, setpoint_c: float | None = None): return self._req("POST", "/camera/cooler", {"on": on, "setpoint_c": setpoint_c})
    def binning(self, n: int): return self._req("POST", "/camera/binning", {"binning": n})
    def set_filter(self, name: str): return self._req("POST", "/filter", {"name": name})
    def focus_move(self, pos: int): return self._req("POST", "/focuser/move", {"position": pos})
    def autofocus(self): return self._req("POST", "/focuser/autofocus")
    def shutter_open(self): return self._req("POST", "/dome/open")
    def shutter_close(self): return self._req("POST", "/dome/close")
    def dome_slew(self, az_deg: float): return self._req("POST", "/dome/slew", {"az_deg": az_deg})
    def dome_slaved(self, on: bool): return self._req("POST", "/dome/slaved", {"slaved": on})
    def sequence_start(self, targets: list[dict], options: dict | None = None):
        return self._req("POST", "/sequence/start", {"targets": targets, "options": options or {}})
    def sequence_stop(self): return self._req("POST", "/sequence/stop")
