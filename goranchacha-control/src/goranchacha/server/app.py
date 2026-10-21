"""API REST del observatorio. Autenticación por token, autorización por rol."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..auth import ROLES, TokenSigner, UserStore
from ..devices.base import DeviceError
from ..observatory import Observatory, SafetyError
from ..scheduler import SequenceOptions, Target


class Login(BaseModel):
    username: str
    password: str


class SlewReq(BaseModel):
    ra_h: float = Field(ge=0, lt=24)
    dec_deg: float = Field(ge=-90, le=90)


class TrackingReq(BaseModel):
    on: bool


class ExposeReq(BaseModel):
    duration_s: float = Field(ge=0, le=3600)
    image_type: str = Field("Light", pattern="^(Light|Dark|Bias|Flat)$")
    object_name: str = Field("", max_length=64)


class CoolerReq(BaseModel):
    on: bool
    setpoint_c: Optional[float] = Field(None, ge=-60, le=30)


class BinningReq(BaseModel):
    binning: int = Field(ge=1, le=4)


class FilterReq(BaseModel):
    name: Optional[str] = None
    position: Optional[int] = None


class FocusReq(BaseModel):
    position: int = Field(ge=0)


class AzimuthReq(BaseModel):
    az_deg: float


class SlavedReq(BaseModel):
    slaved: bool


class SequenceReq(BaseModel):
    targets: list[Target]
    options: SequenceOptions = SequenceOptions()


def create_app(obs: Observatory, users: UserStore, signer: TokenSigner) -> FastAPI:
    app = FastAPI(title="Observatorio Goranchacha", version="0.1.0")
    if obs.cfg.server.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=obs.cfg.server.cors_origins,
                           allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def invalidate_status_cache(request: Request, call_next):
        response = await call_next(request)
        if request.method != "GET":
            obs.invalidate_status()  # que el siguiente GET /status refleje el comando
        return response

    def auth(role: str):
        need = ROLES[role]

        def dep(request: Request) -> dict:
            h = request.headers.get("authorization", "")
            claims = signer.verify(h[7:]) if h.lower().startswith("bearer ") else None
            if not claims:
                raise HTTPException(401, "Token ausente o inválido", headers={"WWW-Authenticate": "Bearer"})
            if ROLES[claims["role"]] < need:
                raise HTTPException(403, f"Se requiere rol {role}")
            return claims

        return dep

    viewer, operator, admin = auth("viewer"), auth("operator"), auth("admin")

    @app.exception_handler(SafetyError)
    async def _safety(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(DeviceError)
    async def _device(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=502)

    def audit(claims: dict, msg: str) -> None:
        obs.bus.info("usuario", f"{claims['sub']} ({claims['role']}): {msg}")

    # ---- autenticación
    @app.post("/auth/login")
    def login(body: Login):
        role = users.verify(body.username, body.password)
        if role is None:
            raise HTTPException(401, "Credenciales inválidas o cuenta bloqueada temporalmente")
        obs.bus.info("usuario", f"Inicio de sesión: {body.username} ({role})")
        return {"token": signer.issue(body.username, role), "role": role, "expires_in": signer.ttl_s}

    # ---- lectura
    @app.get("/status")
    def status(_: dict = Depends(viewer)):
        return obs.status()

    @app.get("/logbook")
    def logbook(limit: int = 200, _: dict = Depends(viewer)):
        return obs.bus.logbook.recent(min(limit, 1000)) if obs.bus.logbook else []

    # ---- seguridad / emergencia
    @app.post("/emergency/close")
    def emergency(claims: dict = Depends(operator)):
        audit(claims, "cierre de emergencia")
        import threading
        threading.Thread(target=obs.emergency_close, args=(f"solicitado por {claims['sub']}",), daemon=True).start()
        return {"ok": True}

    @app.post("/observatory/open")
    def open_obs(claims: dict = Depends(operator)):
        audit(claims, "abrir observatorio")
        obs.open_observatory()
        return {"ok": True}

    @app.post("/observatory/close")
    def close_obs(claims: dict = Depends(operator)):
        audit(claims, "cerrar observatorio")
        import threading
        threading.Thread(target=obs.close_observatory, daemon=True).start()
        return {"ok": True}

    # ---- montura
    @app.post("/mount/slew")
    def slew(b: SlewReq, claims: dict = Depends(operator)):
        audit(claims, f"apuntar a {b.ra_h:.4f} h {b.dec_deg:+.3f}°")
        obs.slew(b.ra_h, b.dec_deg)
        return {"ok": True}

    @app.post("/mount/abort")
    def abort_slew(claims: dict = Depends(operator)):
        obs.dev.mount.abort_slew()
        audit(claims, "abortar apuntado")
        return {"ok": True}

    @app.post("/mount/park")
    def park(claims: dict = Depends(operator)):
        obs.dev.mount.park()
        audit(claims, "estacionar")
        return {"ok": True}

    @app.post("/mount/unpark")
    def unpark(claims: dict = Depends(operator)):
        obs._require_safe("Desestacionar")
        obs.dev.mount.unpark()
        audit(claims, "desestacionar")
        return {"ok": True}

    @app.post("/mount/tracking")
    def tracking(b: TrackingReq, claims: dict = Depends(operator)):
        obs.dev.mount.set_tracking(b.on)
        audit(claims, f"seguimiento {'on' if b.on else 'off'}")
        return {"ok": True}

    # ---- cámara
    @app.post("/camera/expose")
    def expose(b: ExposeReq, claims: dict = Depends(operator)):
        audit(claims, f"exposición {b.image_type} {b.duration_s:g}s")
        obs.start_exposure_async(b.duration_s, b.image_type, b.object_name)
        return {"ok": True}

    @app.post("/camera/abort")
    def abort_exp(claims: dict = Depends(operator)):
        obs.abort_current_exposure()
        audit(claims, "abortar exposición")
        return {"ok": True}

    @app.post("/camera/cooler")
    def cooler(b: CoolerReq, claims: dict = Depends(operator)):
        obs.dev.camera.set_cooler(b.on, b.setpoint_c)
        audit(claims, f"enfriador {'on' if b.on else 'off'} {b.setpoint_c}")
        return {"ok": True}

    @app.post("/camera/binning")
    def binning(b: BinningReq, claims: dict = Depends(operator)):
        obs.dev.camera.set_binning(b.binning)
        return {"ok": True}

    # ---- filtros / enfocador
    @app.post("/filter")
    def set_filter(b: FilterReq, claims: dict = Depends(operator)):
        if (b.name is None) == (b.position is None):
            raise HTTPException(422, "Indicar 'name' o 'position'")
        try:
            obs.set_filter(b.name if b.name is not None else b.position)
        except ValueError:
            raise HTTPException(422, "Filtro desconocido")
        audit(claims, f"filtro {b.name or b.position}")
        return {"ok": True}

    @app.post("/focuser/move")
    def focus_move(b: FocusReq, claims: dict = Depends(operator)):
        obs.dev.focuser.move_to(b.position)
        audit(claims, f"enfocador a {b.position}")
        return {"ok": True}

    @app.post("/focuser/autofocus")
    def autofocus(claims: dict = Depends(operator)):
        import threading
        if obs.sequencer.running or obs.camera_lock.locked():
            raise HTTPException(409, "Cámara ocupada")
        audit(claims, "autoenfoque")

        def run():
            try:
                obs.run_autofocus()
            except Exception as exc:
                obs.bus.error("enfoque", str(exc))

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    # ---- domo
    @app.post("/dome/open")
    def dome_open(claims: dict = Depends(operator)):
        obs.open_shutter()
        audit(claims, "abrir obturador")
        return {"ok": True}

    @app.post("/dome/close")
    def dome_close(claims: dict = Depends(operator)):
        obs.close_shutter()
        audit(claims, "cerrar obturador")
        return {"ok": True}

    @app.post("/dome/slew")
    def dome_slew(b: AzimuthReq, claims: dict = Depends(operator)):
        obs.dev.dome.slew_to_azimuth(b.az_deg)
        return {"ok": True}

    @app.post("/dome/slaved")
    def dome_slaved(b: SlavedReq, claims: dict = Depends(operator)):
        obs.dome_slaved = b.slaved
        audit(claims, f"domo esclavizado {b.slaved}")
        return {"ok": True}

    # ---- secuencias
    @app.post("/sequence/start")
    def seq_start(b: SequenceReq, claims: dict = Depends(operator)):
        audit(claims, f"iniciar secuencia ({len(b.targets)} objetivos)")
        obs.sequencer.start(b.targets, b.options)
        return {"ok": True}

    @app.post("/sequence/stop")
    def seq_stop(claims: dict = Depends(operator)):
        audit(claims, "detener secuencia")
        obs.sequencer.stop(wait=False)
        return {"ok": True}

    @app.get("/sequence")
    def seq_status(_: dict = Depends(viewer)):
        return obs.sequencer.status()

    return app
