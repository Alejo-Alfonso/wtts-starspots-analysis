"""Interfaz de escritorio (PySide6). Todas las llamadas de red van a un hilo aparte."""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..client.api import ApiError, ObservatoryClient
from ..coords import format_dec, format_ra, parse_dec_degrees, parse_ra_hours

POLL_MS = 2000
CONTROL_ROLES = ("operator", "admin")


class _Signals(QObject):
    done = Signal(object, object)  # (resultado, error)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any], on_done: Callable[[Any, Optional[Exception]], None]):
        super().__init__()
        self.fn, self.signals = fn, _Signals()
        self.signals.done.connect(on_done)  # se entrega en el hilo de la GUI

    def run(self) -> None:
        try:
            self.signals.done.emit(self.fn(), None)
        except Exception as exc:
            self.signals.done.emit(None, exc)


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Observatorio Goranchacha — Conexión")
        self.url = QLineEdit("https://localhost:8443")
        self.user, self.pw = QLineEdit(), QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.ca = QLineEdit()
        self.ca.setPlaceholderText("Certificado CA (opcional, .pem)")
        self.verify = QCheckBox("Verificar certificado TLS")
        self.verify.setChecked(True)
        f = QFormLayout(self)
        f.addRow("Servidor", self.url)
        f.addRow("Usuario", self.user)
        f.addRow("Contraseña", self.pw)
        f.addRow("CA", self.ca)
        f.addRow(self.verify)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def make_client(self) -> ObservatoryClient:
        verify: bool | str = self.ca.text().strip() or self.verify.isChecked()
        return ObservatoryClient(self.url.text().strip(), verify=verify)


class MainWindow(QMainWindow):
    def __init__(self, client: ObservatoryClient):
        super().__init__()
        self.client = client
        self.pool = QThreadPool.globalInstance()
        self._tasks: set[_Task] = set()  # evita que el GC destruya señales aún no entregadas
        self.setWindowTitle(f"Observatorio Astronómico Goranchacha — {client.role}")
        self.resize(1000, 700)
        self._controls: list[QWidget] = []
        self._busy_poll = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        top = QHBoxLayout()
        self.banner = QLabel("Conectando…")
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet("font-weight:bold; padding:6px; border-radius:4px;")
        self.emergency = QPushButton("CIERRE DE EMERGENCIA")
        self.emergency.setStyleSheet("background:#b00020; color:white; font-weight:bold; padding:8px 16px;")
        self.emergency.clicked.connect(self._emergency)
        self._controls.append(self.emergency)
        top.addWidget(self.banner, 1)
        top.addWidget(self.emergency)
        root.addLayout(top)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_dashboard()
        self._build_mount()
        self._build_camera()
        self._build_dome()
        self._build_sequence()
        self._build_log()
        self.statusBar().showMessage("Listo")

        if client.role not in CONTROL_ROLES:
            for w in self._controls:
                w.setEnabled(False)
            self.statusBar().showMessage("Rol de solo lectura: los controles están desactivados")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(POLL_MS)
        self._poll()

    # ------------------------------------------------------------ utilidades
    def _ctl(self, w: QWidget) -> QWidget:
        self._controls.append(w)
        return w

    def _btn(self, text: str, fn: Callable[[], Any], parse: Optional[Callable[[], tuple]] = None) -> QPushButton:
        b = QPushButton(text)

        def clicked() -> None:
            try:
                args = parse() if parse else ()
            except ValueError as exc:
                self._error(str(exc))
                return
            self._call(lambda: fn(*args), text)

        b.clicked.connect(clicked)
        return self._ctl(b)

    def _submit(self, fn: Callable[[], Any], on_done: Callable[[Any, Optional[Exception]], None]) -> None:
        task: _Task

        def finished(res, err):
            self._tasks.discard(task)
            on_done(res, err)

        task = _Task(fn, finished)
        self._tasks.add(task)
        self.pool.start(task)

    def _call(self, fn: Callable[[], Any], what: str = "") -> None:
        def done(_res, err):
            if err is not None:
                self._error(f"{what}: {err}" if what else str(err))
            else:
                self.statusBar().showMessage(f"{what}: OK", 4000)
                self._poll()

        self._submit(fn, done)

    def _error(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 10000)
        QMessageBox.warning(self, "Aviso", msg)

    # ------------------------------------------------------------ pestañas
    def _build_dashboard(self) -> None:
        w = QWidget()
        g = QGridLayout(w)
        self.lbl: dict[str, QLabel] = {}
        rows = ["Sitio", "Sol (alt.)", "Montura", "Obturador", "Domo (az.)", "Cámara", "Filtro", "Enfocador", "Secuencia"]
        for i, k in enumerate(rows):
            g.addWidget(QLabel(f"<b>{k}</b>"), i, 0)
            self.lbl[k] = QLabel("—")
            g.addWidget(self.lbl[k], i, 1)
        self.weather = QPlainTextEdit(readOnly=True)
        self.weather.setMaximumHeight(160)
        g.addWidget(QLabel("<b>Meteorología y seguridad</b>"), len(rows), 0, 1, 2)
        g.addWidget(self.weather, len(rows) + 1, 0, 1, 2)
        g.setRowStretch(len(rows) + 2, 1)
        self.tabs.addTab(w, "Panel")

    def _build_mount(self) -> None:
        w = QWidget()
        f = QFormLayout(w)
        self.ra, self.dec = QLineEdit("05:34:32"), QLineEdit("+22:00:52")
        self._ctl(self.ra), self._ctl(self.dec)
        f.addRow("AR (h o hh:mm:ss)", self.ra)
        f.addRow("Dec (° o ±dd:mm:ss)", self.dec)
        row = QHBoxLayout()
        row.addWidget(self._btn("Apuntar", self.client.slew, lambda: (parse_ra_hours(self.ra.text()), parse_dec_degrees(self.dec.text()))))
        row.addWidget(self._btn("Abortar", self.client.abort_slew))
        row.addWidget(self._btn("Estacionar", self.client.park))
        row.addWidget(self._btn("Desestacionar", self.client.unpark))
        row.addWidget(self._btn("Seguimiento ON", lambda: self.client.tracking(True)))
        row.addWidget(self._btn("Seguimiento OFF", lambda: self.client.tracking(False)))
        f.addRow(row)
        self.tabs.addTab(w, "Montura")

    def _build_camera(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        g1 = QGroupBox("Exposición")
        f = QFormLayout(g1)
        self.exp_s = self._ctl(QDoubleSpinBox())
        self.exp_s.setRange(0, 3600), self.exp_s.setValue(10)
        self.exp_type = self._ctl(QComboBox())
        self.exp_type.addItems(["Light", "Dark", "Bias", "Flat"])
        self.exp_obj = self._ctl(QLineEdit())
        f.addRow("Duración (s)", self.exp_s)
        f.addRow("Tipo", self.exp_type)
        f.addRow("Objeto", self.exp_obj)
        row = QHBoxLayout()
        row.addWidget(self._btn("Exponer", self.client.expose,
                                lambda: (self.exp_s.value(), self.exp_type.currentText(), self.exp_obj.text())))
        row.addWidget(self._btn("Abortar", self.client.abort_exposure))
        f.addRow(row)
        self.exp_bar = QProgressBar()
        f.addRow(self.exp_bar)
        v.addWidget(g1)

        g2 = QGroupBox("Sensor")
        f2 = QFormLayout(g2)
        self.setpoint = self._ctl(QDoubleSpinBox())
        self.setpoint.setRange(-60, 30), self.setpoint.setValue(-20)
        self.binning = self._ctl(QSpinBox())
        self.binning.setRange(1, 4)
        f2.addRow("Temperatura objetivo (°C)", self.setpoint)
        row2 = QHBoxLayout()
        row2.addWidget(self._btn("Enfriador ON", self.client.cooler, lambda: (True, self.setpoint.value())))
        row2.addWidget(self._btn("Enfriador OFF", lambda: self.client.cooler(False)))
        f2.addRow(row2)
        f2.addRow("Binning", self.binning)
        f2.addRow(self._btn("Aplicar binning", self.client.binning, lambda: (self.binning.value(),)))
        v.addWidget(g2)

        g3 = QGroupBox("Filtros y enfoque")
        f3 = QFormLayout(g3)
        self.filter_box = self._ctl(QComboBox())
        f3.addRow("Filtro", self.filter_box)
        f3.addRow(self._btn("Cambiar filtro", self.client.set_filter, lambda: (self.filter_box.currentText(),)))
        self.focus_pos = self._ctl(QSpinBox())
        self.focus_pos.setRange(0, 1_000_000)
        f3.addRow("Posición enfocador", self.focus_pos)
        row3 = QHBoxLayout()
        row3.addWidget(self._btn("Mover", self.client.focus_move, lambda: (self.focus_pos.value(),)))
        row3.addWidget(self._btn("Autoenfoque", self.client.autofocus))
        f3.addRow(row3)
        v.addWidget(g3)
        v.addStretch(1)
        self.tabs.addTab(w, "Cámara / Filtros / Enfoque")

    def _build_dome(self) -> None:
        w = QWidget()
        f = QFormLayout(w)
        row = QHBoxLayout()
        row.addWidget(self._btn("Abrir observatorio", self.client.open_observatory))
        row.addWidget(self._btn("Cerrar observatorio", self.client.close_observatory))
        f.addRow(row)
        row2 = QHBoxLayout()
        row2.addWidget(self._btn("Abrir obturador", self.client.shutter_open))
        row2.addWidget(self._btn("Cerrar obturador", self.client.shutter_close))
        f.addRow(row2)
        self.az = self._ctl(QDoubleSpinBox())
        self.az.setRange(0, 360)
        f.addRow("Azimut (°)", self.az)
        f.addRow(self._btn("Girar domo", self.client.dome_slew, lambda: (self.az.value(),)))
        self.slaved = self._ctl(QCheckBox("Domo esclavizado a la montura"))
        self.slaved.setChecked(True)
        self.slaved.clicked.connect(lambda on: self._call(lambda: self.client.dome_slaved(on), "Domo esclavizado"))
        f.addRow(self.slaved)
        self.tabs.addTab(w, "Domo")

    def _build_sequence(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        cols = ["Objeto", "AR", "Dec", "Filtro", "Exp (s)", "N", "Prior.", "Alt. mín"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self._ctl(self.table)
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, fn in (("Añadir fila", self._add_row), ("Quitar fila", self._del_row),
                         ("Guardar…", self._save_plan), ("Cargar…", self._load_plan)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(self._ctl(b))
        self.opt_dark = self._ctl(QCheckBox("Esperar a la noche astronómica"))
        self.opt_dark.setChecked(True)
        row.addWidget(self.opt_dark)
        row.addWidget(self._btn("Iniciar secuencia", self.client.sequence_start, self._plan_args))
        row.addWidget(self._btn("Detener", self.client.sequence_stop))
        v.addLayout(row)
        self.seq_lbl = QLabel("—")
        v.addWidget(self.seq_lbl)
        self._add_row(["Objetivo 1", "05:34:32", "+22:00:52", "R", "30", "10", "5", "30"])
        self.tabs.addTab(w, "Secuencia")

    def _add_row(self, values=None) -> None:
        values = values if isinstance(values, list) else ["", "", "", "R", "30", "10", "5", "30"]
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, val in enumerate(values):
            self.table.setItem(r, c, QTableWidgetItem(val))

    def _del_row(self) -> None:
        if self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def _plan_args(self) -> tuple:
        targets = []
        for r in range(self.table.rowCount()):
            t = [(self.table.item(r, c).text() if self.table.item(r, c) else "").strip() for c in range(8)]
            if not t[0]:
                raise ValueError(f"Fila {r + 1}: falta el nombre del objeto")
            targets.append(dict(
                name=t[0], ra_h=parse_ra_hours(t[1]), dec_deg=parse_dec_degrees(t[2]), priority=int(t[6]),
                min_altitude_deg=float(t[7]),
                exposures=[dict(image_type="Light", filter=t[3] or None, exposure_s=float(t[4]), count=int(t[5]))]))
        if not targets:
            raise ValueError("Agregue al menos un objetivo")
        return targets, {"require_dark": self.opt_dark.isChecked()}

    def _save_plan(self) -> None:
        try:
            targets, _ = self._plan_args()
        except ValueError as exc:
            return self._error(str(exc))
        path, _ = QFileDialog.getSaveFileName(self, "Guardar plan", "plan.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(targets, fh, indent=2, ensure_ascii=False)

    def _load_plan(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar plan", "", "JSON (*.json)")
        if not path:
            return
        with open(path, encoding="utf-8") as fh:
            targets = json.load(fh)
        self.table.setRowCount(0)
        for t in targets:
            e = t["exposures"][0]
            self._add_row([t["name"], format_ra(t["ra_h"]), format_dec(t["dec_deg"]), e.get("filter") or "",
                           str(e["exposure_s"]), str(e["count"]), str(t.get("priority", 5)),
                           str(t.get("min_altitude_deg", 30))])

    def _build_log(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(2000)
        v.addWidget(self.log)
        self.tabs.addTab(w, "Bitácora")
        self._last_log_poll = 0

    # ------------------------------------------------------------ sondeo
    def _emergency(self) -> None:
        if QMessageBox.question(self, "Cierre de emergencia",
                                "¿Estacionar la montura y cerrar el observatorio ahora?") == QMessageBox.Yes:
            self._call(self.client.emergency_close, "Cierre de emergencia")

    def _poll(self) -> None:
        if self._busy_poll:
            return
        self._busy_poll = True

        def fetch():
            return self.client.status(), self.client.logbook(100)

        def done(res, err):
            self._busy_poll = False
            if err is not None:
                self.banner.setText(f"SIN CONEXIÓN: {err}")
                self.banner.setStyleSheet("background:#b00020; color:white; font-weight:bold; padding:6px;")
                return
            self._render(*res)

        self._submit(fetch, done)

    def _render(self, s: dict, events: list) -> None:
        safe = s["safety"]
        if safe["safe"]:
            self.banner.setText("CONDICIONES SEGURAS" + ("" if safe["can_open"] else " (estabilizando)"))
            self.banner.setStyleSheet("background:#1b5e20; color:white; font-weight:bold; padding:6px;")
        else:
            self.banner.setText("INSEGURO: " + "; ".join(safe["reasons"]))
            self.banner.setStyleSheet("background:#b00020; color:white; font-weight:bold; padding:6px;")
        L, m, c, fw, fo, d, q = self.lbl, s["mount"], s["camera"], s["filterwheel"], s["focuser"], s["dome"], s["sequence"]
        L["Sitio"].setText(s["site"])
        L["Sol (alt.)"].setText("—" if s["sun_altitude_deg"] is None else f"{s['sun_altitude_deg']:.1f}°")
        L["Montura"].setText(m.get("error") or (f"AR {format_ra(m['ra_h'])}  Dec {format_dec(m['dec_deg'])}  "
                             f"{'apuntando' if m['slewing'] else 'seguimiento' if m['tracking'] else 'parada'}"
                             f"{'  [ESTACIONADA]' if m['parked'] else ''}"))
        L["Obturador"].setText(d.get("error") or d["shutter"])
        L["Domo (az.)"].setText(d.get("error") or f"{d['azimuth_deg']:.1f}°{'  (girando)' if d['slewing'] else ''}")
        L["Cámara"].setText(c.get("error") or f"{c['state']}  T={c['temperature_c']:.1f}°C  "
                            f"enfriador {'ON' if c['cooler_on'] else 'OFF'}  bin {c['binning']}")
        L["Filtro"].setText(fw.get("error") or fw["current"])
        L["Enfocador"].setText(fo.get("error") or f"{fo['position']}" + ("  (moviendo)" if fo["moving"] else ""))
        L["Secuencia"].setText(f"{q['state']} {q['message']}  [{q['frames_done']}/{q['frames_total']}]  {q['target'] or ''}")
        self.seq_lbl.setText(L["Secuencia"].text())
        self.exp_bar.setValue(int(c.get("progress", 0) * 100) if "progress" in c else 0)
        w = s.get("weather") or {}
        self.weather.setPlainText("\n".join(f"{k}: {v}" for k, v in w.items() if k != "timestamp"))
        if fw.get("names") and self.filter_box.count() != len(fw["names"]):
            self.filter_box.clear()
            self.filter_box.addItems(fw["names"])
        text = "\n".join(f"{e['ts']} [{e['level']}] {e['source']}: {e['message']}" for e in reversed(events))
        if text != getattr(self, "_log_text", None):
            self._log_text = text
            self.log.setPlainText(text)


def run() -> None:
    import sys
    app = QApplication(sys.argv)
    while True:
        dlg = LoginDialog()
        if dlg.exec() != QDialog.Accepted:
            return
        client = dlg.make_client()
        try:
            client.login(dlg.user.text(), dlg.pw.text())
            break
        except ApiError as exc:
            QMessageBox.critical(None, "No se pudo conectar", str(exc))
    win = MainWindow(client)
    win.show()
    sys.exit(app.exec())
