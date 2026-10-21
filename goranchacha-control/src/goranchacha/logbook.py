"""Bitácora persistente (SQLite) y bus de eventos en memoria."""
from __future__ import annotations

import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class Logbook:
    def __init__(self, db_path: str | Path):
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
                "level TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL)"
            )
            self._db.commit()

    def add(self, level: str, source: str, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._db.execute(
                "INSERT INTO events (ts, level, source, message) VALUES (?,?,?,?)",
                (ts, level, source, message),
            )
            self._db.commit()

    def recent(self, limit: int = 200, min_id: int = 0) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, ts, level, source, message FROM events WHERE id > ? "
                "ORDER BY id DESC LIMIT ?",
                (min_id, limit),
            ).fetchall()
        return [dict(id=r[0], ts=r[1], level=r[2], source=r[3], message=r[4]) for r in rows]


class EventBus:
    """Publica eventos a la bitácora y a un buffer circular para los clientes."""

    def __init__(self, logbook: Logbook | None = None, buffer: int = 500):
        self.logbook = logbook
        self._listeners: list[Callable[[dict], None]] = []
        self._buf: deque[dict] = deque(maxlen=buffer)

    def subscribe(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def publish(self, level: str, source: str, message: str) -> None:
        ev = dict(t=time.time(), level=level, source=source, message=message)
        self._buf.append(ev)
        if self.logbook:
            self.logbook.add(level, source, message)
        for fn in list(self._listeners):
            try:
                fn(ev)
            except Exception:  # un listener defectuoso no debe afectar al control
                pass

    def info(self, source: str, message: str) -> None:
        self.publish("INFO", source, message)

    def warning(self, source: str, message: str) -> None:
        self.publish("WARNING", source, message)

    def error(self, source: str, message: str) -> None:
        self.publish("ERROR", source, message)
