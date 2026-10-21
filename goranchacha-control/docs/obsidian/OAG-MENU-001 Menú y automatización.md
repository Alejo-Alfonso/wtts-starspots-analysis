---
id: OAG-MENU-001
tipo: especificacion
estado: borrador-pendiente-de-aprobacion
fecha: 2026-10-21
sesion: OAG-SES-2026-10-21-01
tags: [OAG, menu, automatizacion]
---

# OAG-MENU-001 — Menú de la aplicación y nivel de automatización

Parte de [[OAG-PLAN-001 Plan del proyecto]].

## Leyenda del nivel de automatización

| Etiqueta | Significado |
|---|---|
| **AUTO** | Puede ejecutarse sin intervención una vez disponible el código y cumplidos los prerrequisitos |
| **SEMI** | El software ejecuta, pero requiere una acción o decisión humana en puntos concretos |
| **MANUAL** | Lo hace una persona; la aplicación solo lo registra o lo guía |
| **BLOQUEADO** | Hoy no puede ejecutarse por un dato/prueba PENDIENTE (se indica cuál) |

«Hoy» se refiere a lo que el hardware y los datos confirmados permiten; **aún no existe código**. Cada opción muestra su etiqueta, sus prerrequisitos y, si está bloqueada, **la compuerta que falta**. Cada opción es un objeto del registro `menu` con: `id`, `bloque`, `nivel`, `prerrequisitos`, `compuertas`, `ejecutar()`.

## Bloque A — Captura

| ID | Opción | Nivel hoy | Prerrequisitos / qué requiere de una persona | Compuerta pendiente |
|---|---|---|---|---|
| A1 | Estado y conexión de equipos (vista por equipo) | **AUTO** | Equipos encendidos y USB/COM presentes | — |
| A2 | Conectar y probar **enfocador** (COM7) | **AUTO** | — (confirmado funcional) | — |
| A3 | Conectar y probar **montura** (COM6; lectura de estado, sin movimiento) | **AUTO** | Montura encendida | — |
| A4 | **Prueba de GoTo** | **BLOQUEADO** → SEMI | Persona presente, telescopio libre y alineado, cielo/horizonte despejado | Prueba de GoTo PENDIENTE |
| A5 | Conectar y probar **rueda de filtros** (movimiento a cada posición) | **AUTO** | Cámara/rueda sin obstrucciones | — |
| A6 | **Verificar/confirmar el orden de filtros** | **MANUAL** (la app guía y registra) | Inspección física de la rueda o prueba con fuente conocida; el usuario confirma en `filtros.yaml` | Orden PENDIENTE |
| A7 | Conectar y probar **cámara** (enfriar, bias de prueba, lectura de cabeceras) | **AUTO** | Cámara conectada | — |
| A8 | **Bias** (N cuadros) | **AUTO** | Temperatura estable | — |
| A9 | **Darks** (por tiempo de exposición) | **BLOQUEADO** → AUTO | Obturador cerrado o cámara tapada (según cámara) | Prueba de darks PENDIENTE |
| A10 | **Flats por filtro** | **SEMI** | Fuente de flats (crepúsculo o pantalla), apuntado, decisión de cielo; la app ajusta la exposición al nivel objetivo | Orden de filtros y fuente de flats PENDIENTES |
| A11 | **Autoenfoque / foco por filtro** | **SEMI** | Campo estelar apuntado; validación del resultado por el operador | Parfocalidad entre filtros PENDIENTE |
| A12 | **Revisión de lista de campos Landolt** | **MANUAL** | El usuario revisa `landolt_campos.yaml` y marca `revisado-por-usuario` | Lista no elegida |
| A13 | **Secuencia de campo Landolt** (por filtro, N exposiciones, registro de X) | **SEMI** | Cielo despejado, cúpula/techo abierto por una persona, apuntado verificado; la app ejecuta la secuencia y escribe `AIRMASS` | Orden de filtros, GoTo, lista Landolt, flats/bias/darks de la noche |
| A14 | **Registro de masa de aire X** | **AUTO** | Hora y posición | — (se ejecuta dentro de A13) |
| A15 | **Nota de sesión** `OAG-SES-…` (condiciones, incidencias, guiado sí/no) | **SEMI** | La app crea la plantilla; el operador completa condiciones | — |

## Bloque B — Procesamiento

| ID | Opción | Nivel hoy | Prerrequisitos | Compuerta pendiente |
|---|---|---|---|---|
| B1 | **Calibración de imágenes** (masters de bias/dark/flat y aplicación) | **AUTO** | Bias, darks y flats de la sesión | Darks PENDIENTES para datos reales |
| B2 | **Resolución astrométrica** (WCS) | **AUTO** (con herramienta elegida) | Solucionador instalado (D-05); pista de coordenadas y escala | Escala de placa/reductor PENDIENTE |
| B3 | **Correspondencia con estándares Landolt** | **AUTO** | Lista `revisado-por-usuario` y WCS | Lista no elegida |
| B4 | **Fotometría de apertura** (radio y anillo configurables) | **AUTO** | Imágenes calibradas + WCS + parámetros | — |
| B5 | **Control de calidad** (saturación, SNR, X, cobertura) | **AUTO** | Resultado de B4 | — |
| B6 | **Ajuste de Z y k′ por filtro** | **AUTO** | B4–B5 y cobertura de X suficiente | Datos reales PENDIENTES |
| B7 | **Decisión de validez de la noche (fotométrica sí/no)** | **SEMI** | La app propone con criterios; el usuario decide | — |
| B8 | **Reporte Markdown** para la bóveda `OAG-UPTC` | **AUTO** | B6–B7 | — |

## Reglas transversales del menú

1. Cada equipo se conecta y prueba **por separado** (A2, A3, A5, A7); ninguna opción exige que todos estén conectados salvo A13.
2. Si un módulo falla, el menú **sigue funcionando**; la opción afectada muestra «FALLA: motivo» y las demás permanecen disponibles.
3. Toda ejecución registra `OAG-SES-…`, hora, usuario y resultado en `log/`.
4. Una opción **BLOQUEADA** nunca se ejecuta «por si acaso»: explica qué dato falta y cómo confirmarlo.
