---
id: OAG-DEP-001
tipo: dependencias
estado: borrador-pendiente-de-aprobacion
fecha: 2026-10-21
sesion: OAG-SES-2026-10-21-01
tags: [OAG, pendientes, hardware, decisiones]
---

# OAG-DEP-001 — Dependencias de hardware y decisiones pendientes

Parte de [[OAG-PLAN-001 Plan del proyecto]]. **Estado `PENDIENTE` = no hecho ni confirmado.** Responsable y fecha se dejan para que el usuario los complete.

## 1. Pendientes de hardware / pruebas

| ID | Pendiente | Bloquea | Cómo se resuelve | Resp. | Fecha | Estado |
|---|---|---|---|---|---|---|
| D-02 | **Orden físico de filtros en la rueda** (7 posiciones, 5 filtros U B V R I; 2 posiciones sin asignar) | A6, A10, A13, todo el ajuste por filtro | Inspección física; luego registrar en `filtros.yaml` y marcar `confirmado`. Verificación adicional con cuadros de cielo/flat (el U debe dar mucha menos señal) | | | **PENDIENTE** |
| D-03 | **Reductor óptico**: ¿se usa? ¿qué factor? → escala de placa y campo de visión | Elección de campos Landolt, parámetros de apertura en segundos de arco, astrometría | Confirmar configuración óptica real; medir la escala con una imagen resuelta | | | **PENDIENTE** |
| D-08a | **Prueba de GoTo** de la montura | A4, A13 | Prueba supervisada, telescopio libre, procedimiento documentado | | | **PENDIENTE** |
| D-08b | **Prueba de darks** | A9, F3-02 | Ver F3-02 | | | **PENDIENTE** |
| D-04 | **Ganancia (e⁻/ADU), ruido de lectura, linealidad y saturación** de la G2-8300 en este montaje | Incertidumbres fotométricas, umbral de saturación | Medirlas (método de transferencia de fotones) o tomarlas de la hoja del fabricante y marcarlas como «del fabricante» | | | **PENDIENTE** |
| D-07 | **Fuente de flats** (crepuscular, pantalla/caja de luz) | A10, F3-03 | Decidir y documentar el procedimiento | | | **PENDIENTE** |
| — | **Parfocalidad** entre filtros (desplazamiento de enfoque) | A11 | Medir el foco óptimo por filtro con el enfocador y guardar offsets | | | **PENDIENTE** |
| — | ¿La G2-8300 tiene **obturador mecánico**? | Método de darks | Confirmar con el manual/driver (no se asume) | | | **PENDIENTE** |
| — | **ProgID exactos** de los drivers ASCOM | Conexión | Obtenerlos con el *Chooser* de ASCOM en el PC; no se deducen de los nombres | | | **PENDIENTE** |
| — | **Versión de ASCOM Platform** y Python **64 bits** (los drivers indicados son de 64 bits) | Conexión | Verificar en el PC | | | **PENDIENTE** |
| — | **Números COM** estables (COM6 montura, COM7 enfocador) | Conexión | Fijar por driver/ID de dispositivo; verificar al arrancar | | | Datos dados; **verificar en el PC** |
| — | **PHD2 / guiado** con la ASI120MC-S | Exposiciones largas con buen seguimiento | En curso por el usuario; la v1 solo anota si se guió | | | En curso (fuera de alcance) |
| — | **Cambio de la Moravian por cámara planetaria CMOS** | Diseño de la capa de cámara | Modelo y driver aún no definidos; ver riesgos en el plan §6 | | | **PENDIENTE** (futuro) |
| — | **Lista de campos Landolt** | A12, A13, B3 | F4-01/02 | | | **PENDIENTE** |

## 2. Decisiones de diseño abiertas (necesito tu respuesta para aprobar)

| ID | Decisión | Opciones | Recomendación | Respuesta del usuario |
|---|---|---|---|---|
| D-01 | **Conexión con los drivers ASCOM** | (a) COM directo en Windows (pywin32/ASCOM), un proceso trabajador por equipo; (b) Alpaca vía ASCOM Remote (HTTP; ya existe cliente en el v0.1) | **(a)**: menos piezas, drivers ya instalados en el PC. (b) queda como opción futura para acceso remoto | |
| D-05 | **Resolución astrométrica** | ASTAP (CLI, sin internet, necesita base de datos estelar) / astrometry.net local / servicio en línea | **ASTAP**, por simplicidad en Windows y uso sin red; confirmar según FOV (D-03) | |
| D-06 | **Domo/techo y estación meteorológica**: no figuran en el hardware de la v1 | Congelar el código de seguridad automática del v0.1 y operar con persona presente / incorporar el equipo real después | **Congelar**; la seguridad en v1 es responsabilidad del operador | |
| D-09 | **Término de color** en el ajuste | Desactivado (solo Z y k′) / activado | **Desactivado** por defecto, activable en `ajuste.yaml`; el reporte indica cuál se usó | |
| D-10 | **Fórmula de masa de aire** | Pickering 2002 (ya usada) / Hardie / sec z | **Pickering 2002** registrada en la cabecera; verificada contra una referencia independiente (F4-04) | |
| D-11 | **Interfaz del menú** | Consola primero / PySide6 desde el inicio | **Registro de opciones independiente de la interfaz**; consola en F1–F2 y GUI sobre el mismo registro | |
| — | **Umbrales de calidad** (SNR, X máx., RMS, ΔX) | Propuestas en [[OAG-FOT-001 Modelo fotométrico Z y k]] | Aceptar, cambiar o dejar para después de la primera noche | |

## 3. Dependencias de software (a instalar tras la aprobación)

- **Sistema:** Windows 11, ASCOM Platform (versión por confirmar), drivers listados en el plan; Python **64 bits** (propuesta 3.11 o 3.12).
- **Bibliotecas:** `numpy`, `scipy`, `astropy`, `photutils`, `astroquery`, `pydantic`, `pyyaml`, `matplotlib`, `pytest`; `pywin32` (COM, según D-01); opcional `ccdproc`. Solucionador astrométrico según D-05 (p. ej. ASTAP + su base de datos).
- Las versiones exactas se fijan y registran en el reporte de cada sesión.

## 4. Qué NO está en la v1 (para evitar suposiciones)

ASI071MC Pro, ASI224MC Pro, ASI183MC Pro; control de PHD2/ASI120MC-S; domo y clima; acceso remoto; término de color por defecto; extinción de segundo orden.
