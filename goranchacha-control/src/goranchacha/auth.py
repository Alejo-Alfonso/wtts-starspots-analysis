"""Usuarios con roles (viewer < operator < admin) y tokens firmados con HMAC."""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

ROLES = {"viewer": 1, "operator": 2, "admin": 3}
_ITER = 200_000


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER).hex()


class UserStore:
    MAX_FAILS, LOCK_S = 5, 60

    def __init__(self, db_path: str | Path):
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._fails: dict[str, tuple[int, float]] = {}
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, salt TEXT, hash TEXT, role TEXT)")
            self._db.commit()

    def add(self, name: str, password: str, role: str) -> None:
        if role not in ROLES:
            raise ValueError(f"Rol inválido: {role}")
        if len(password) < 10:
            raise ValueError("La contraseña debe tener al menos 10 caracteres")
        salt = os.urandom(16)
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?)", (name, salt.hex(), _hash(password, salt), role))
            self._db.commit()

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def verify(self, name: str, password: str) -> Optional[str]:
        """Devuelve el rol si las credenciales son válidas; None si no (con bloqueo por intentos)."""
        n, until = self._fails.get(name, (0, 0.0))
        if n >= self.MAX_FAILS and time.time() < until:
            return None
        with self._lock:
            row = self._db.execute("SELECT salt, hash, role FROM users WHERE name=?", (name,)).fetchone()
        salt = bytes.fromhex(row[0]) if row else b"\0" * 16  # mismo coste exista o no el usuario
        ok = hmac.compare_digest(_hash(password, salt), row[1] if row else "0" * 64) and row is not None
        if ok:
            self._fails.pop(name, None)
            return row[2]
        self._fails[name] = (n + 1, time.time() + self.LOCK_S)
        return None


class TokenSigner:
    def __init__(self, secret: bytes, ttl_s: int):
        self._secret, self.ttl_s = secret, ttl_s

    @classmethod
    def from_file(cls, path: Path, ttl_s: int) -> "TokenSigner":
        if not path.exists():
            path.write_bytes(secrets.token_bytes(32))
            os.chmod(path, 0o600)
        return cls(path.read_bytes(), ttl_s)

    def issue(self, user: str, role: str) -> str:
        body = base64.urlsafe_b64encode(json.dumps({"sub": user, "role": role, "exp": time.time() + self.ttl_s}).encode()).decode()
        sig = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def verify(self, token: str) -> Optional[dict]:
        try:
            body, sig = token.rsplit(".", 1)
            good = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, good):
                return None
            data = json.loads(base64.urlsafe_b64decode(body))
            return data if data["exp"] > time.time() and data["role"] in ROLES else None
        except Exception:
            return None


def cli() -> None:
    ap = argparse.ArgumentParser(description="Gestión de usuarios del observatorio")
    ap.add_argument("--config", default=None, help="YAML de configuración (para localizar data_dir)")
    ap.add_argument("name")
    ap.add_argument("role", choices=list(ROLES))
    a = ap.parse_args()
    from .config import load_config
    store = UserStore(load_config(a.config).data_path / "usuarios.db")
    pw = getpass.getpass("Contraseña (mín. 10 caracteres): ")
    if pw != getpass.getpass("Repetir: "):
        raise SystemExit("Las contraseñas no coinciden")
    store.add(a.name, pw, a.role)
    print(f"Usuario '{a.name}' ({a.role}) guardado")
