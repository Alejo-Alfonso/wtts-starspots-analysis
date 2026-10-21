---
id: OAG-CHK-001
tipo: checklist
estado: borrador-pendiente-de-aprobacion
fecha: 2026-10-21
sesion: OAG-SES-2026-10-21-01
tags: [OAG, checklist, aceptacion]
---

# OAG-CHK-001 — Checklist y criterios de aceptación

Parte de [[OAG-PLAN-001 Plan del proyecto]]. Casillas vacías = no hecho. Los umbrales numéricos son **propuestas** salvo que se indique lo contrario. **«HW»** = requiere hardware y al usuario presente. Un criterio con HW **no se da por cumplido con simuladores**.

## F0 — Aprobación
- [ ] F0-01 El usuario aprueba el plan y resuelve o acepta como abiertas las decisiones D-01…D-11 ([[OAG-DEP-001 Dependencias pendientes]]). **Criterio:** respuesta escrita del usuario registrada en la nota de sesión `OAG-SES-…`.
- [ ] F0-02 Se acuerda que la v1 corre local y que el código de domo/clima/remoto del v0.1 queda congelado (D-06).

## F1 — Fundaciones (sin HW)
- [ ] F1-01 **Configuración validada.** Criterio: un `equipo.yaml` con dato faltante o inválido produce un error que nombra el campo; pruebas unitarias.
- [ ] F1-02 **Compuertas.** Criterio: con `filtros.yaml` en estado `pendiente`, A10/A13 se rechazan con mensaje que cita el dato faltante; con `confirmado` se permiten (prueba unitaria en ambos sentidos).
- [ ] F1-03 **Identificador de sesión.** Criterio: genera `OAG-SES-AAAA-MM-DD-NN`, `NN` consecutivo por día sin repetirse, aunque haya varias sesiones o reinicios; valida el formato con regex en las pruebas.
- [ ] F1-04 **Aislamiento de módulos (con simuladores).** Criterio: forzar excepción, cuelgue (> timeout) y muerte del proceso de un equipo simulado → los otros tres siguen respondiendo y el menú sigue operativo; el equipo caído pasa a `FALLA` con motivo y puede reiniciarse.
- [ ] F1-05 **Registro del menú.** Criterio: toda opción declara `nivel`, `prerrequisitos` y `compuertas`; una prueba falla si alguna carece de ellos; el menú muestra `BLOQUEADO` con el motivo.
- [ ] F1-06 **Contrato de cabeceras FITS** definido y verificado por una prueba que rechaza FITS sin los campos obligatorios.
- [ ] F1-07 **Pruebas de conformidad de `CameraPort`** que pasa el simulador (base para F2-04 y el futuro CMOS).

## F2 — Conexión equipo por equipo (HW)
Plantilla por equipo: *conectar → leer propiedades → ejecutar un comando seguro → desconectar → provocar fallo (desconectar USB/cerrar driver) → comprobar que los demás equipos no se afectan → reconectar.* Tiempo máximo de respuesta/detección de fallo: **propuesta 10 s**.
- [ ] F2-01 **Enfocador** (COM7): lee posición y temperatura; movimiento pequeño de ida y vuelta ±N pasos devuelve a la posición inicial dentro de la tolerancia del driver. Sin pasos fuera de rango.
- [ ] F2-02 **Montura** (COM6, «SkyWatcher Telescope»): conecta; lee AR/Dec, *parked*, *tracking*; **sin GoTo** mientras la compuerta de GoTo esté pendiente. Se verifica que la hora y ubicación de la montura coinciden con el sitio configurado.
- [ ] F2-03 **Rueda de filtros**: recorre las 7 posiciones y reporta la posición real tras cada movimiento (0 errores en 3 recorridos completos). *No* certifica qué filtro hay en cada posición (eso es A6).
- [ ] F2-04 **Cámara**: conecta, lee capacidades (tamaño, píxel, bits, enfriador), enfría a la temperatura objetivo configurable y la estabiliza (criterio: ±propuesta 0.5 °C durante propuesta 5 min), toma un bias y escribe un FITS que pasa F1-06.
- [ ] F2-05 **Aislamiento real**: con los cuatro conectados, desconectar físicamente cada uno por turnos → el resto sigue operativo y el menú indica cuál falló.
- [ ] F2-06 **Arranque**: tras reiniciar el PC, la verificación de arranque detecta cambios de puerto COM y lo informa sin conectar al equipo equivocado.

## F3 — Calibración (HW)
- [ ] F3-01 **Bias**: N cuadros; la media y la dispersión del master quedan registradas; criterio: sin tendencia con el tiempo (propuesta: pendiente < 1 ADU en la serie) y sin patrones anómalos.
- [ ] F3-02 **Darks** *(bloqueado por «prueba de darks» PENDIENTE)*: primero una prueba documentada de darks (obturador/tapa, estabilidad de temperatura); después, darks por exposición. Criterio: la corriente oscura medida a dos temperaturas coincide con la esperada del sensor dentro de lo razonable y **se documenta** en la nota de sesión.
- [ ] F3-03 **Flats por filtro** *(bloqueado por orden de filtros y fuente de flats)*: nivel objetivo propuesto 30–60 % del rango lineal; ≥ 10 cuadros por filtro; el master de flat normalizado tiene variación pico a pico coherente y sin gradientes imprevistos (se documenta).
- [ ] F3-04 Cada FITS de calibración lleva `SESSID`, `IMAGETYP`, `FILTER` (si aplica), `CCD-TEMP`, `EXPTIME`.

## F4 — Catálogo Landolt y secuencia (HW)
- [ ] F4-01 **Consulta** a VizieR (con astroquery) genera `landolt_campos.yaml` en estado `borrador`, con referencia y fecha de consulta por campo. Criterio: ningún valor proviene del código; reproducir la consulta da el mismo archivo.
- [ ] F4-02 **Filtrado** por declinación/altitud desde el sitio (5.55°N); el resultado se revisa a mano y se pasa a `revisado-por-usuario` **solo por el usuario**.
- [ ] F4-03 **Compuerta de campos:** la secuencia rechaza un campo en `borrador` (prueba unitaria).
- [ ] F4-04 **Masa de aire**: el cálculo se contrasta con una calculadora independiente (p. ej. astropy en otra ruta de código) para 5 pares (hora, objeto): diferencia < 0.005.
- [ ] F4-05 **Secuencia** (con simulador primero, luego HW): para cada filtro del plan, N exposiciones, cambio de filtro verificado por posición, `AIRMASS` y `OAGAIRM` escritos en cada cuadro; abortable en cualquier momento sin dejar equipos en estado indefinido.
- [ ] F4-06 **Enfoque por filtro** registrado en cabecera (`FOCUSPOS`) y en la nota de sesión.

## F5 — Procesamiento (datos reales o sintéticos)
- [ ] F5-01 **Calibración**: con datos sintéticos de verdad conocida, el resultado reproduce la señal inyectada dentro de ruido; con datos reales se inspeccionan masters y un cuadro antes/después.
- [ ] F5-02 **Astrometría**: ≥ 95 % de los cuadros resueltos; error residual del WCS < propuesta 1″ (o < 1 px si la escala aún no se conoce); los cuadros no resueltos se reportan, no se descartan en silencio.
- [ ] F5-03 **Correspondencia**: cada estándar se asigna a una estrella detectada dentro de un radio configurable; ambigüedades y no detecciones listadas.
- [ ] F5-04 **Fotometría de apertura**: con estrellas sintéticas inyectadas (flujo conocido, ruido añadido), el flujo recuperado coincide con el inyectado dentro de lo esperado por el ruido (sesgo < 1 %); radio y anillo se leen de `fotometria.yaml` y se **guardan en cada salida**.
- [ ] F5-05 **Control de calidad**: marca saturación, SNR bajo, bordes y X > umbral con motivo explícito.

## F6 — Ajuste y reporte (sin HW)
- [ ] F6-01 **Ajuste con datos sintéticos** (Z y k′ conocidos + ruido): recupera ambos dentro de 3σ en ≥ 95 % de 1000 realizaciones; los valores y las incertidumbres se validan frente a una implementación de referencia independiente.
- [ ] F6-02 **Rechazos**: filtros sin cobertura (ΔX o N insuficientes) se declaran «no calibrables» y **no** producen Z/k′ (prueba unitaria).
- [ ] F6-03 **Reporte `.md`**: contiene `OAG-SES-…`, versión de software y configuración, mapa de filtros con su estado de confirmación, tabla Z y k′ ± σ por filtro, RMS, cobertura de X, gráficos, estrellas rechazadas y advertencias. Se abre sin errores en Obsidian (frontmatter y enlaces válidos).
- [ ] F6-04 El reporte **no afirma nada marcado PENDIENTE como hecho** (prueba: si una compuerta estaba pendiente, el reporte lo dice).

## F7 — Validación en cielo y cierre (HW)
- [ ] F7-01 **Noche real:** una sesión completa con la secuencia y cobertura de X del plan; resultados con barras de error.
- [ ] F7-02 **Cruce independiente:** comparar al menos una estándar no usada en el ajuste (o un segundo campo) → la diferencia está dentro de lo que predicen las incertidumbres.
- [ ] F7-03 **Reproducibilidad:** reprocesar la misma sesión desde `raw/` da resultados idénticos (mismo hash de salida salvo marca de tiempo).
- [ ] F7-04 **Documentación:** nota de sesión completa, reporte en la bóveda, lista de pendientes actualizada.
- [ ] F7-05 **Cambio de cámara (prueba de diseño, no obligatoria):** el adaptador de una segunda cámara (o un simulador con otras capacidades, p. ej. color/sin enfriador) pasa F1-07 sin modificar `processing` ni `fitting`.
