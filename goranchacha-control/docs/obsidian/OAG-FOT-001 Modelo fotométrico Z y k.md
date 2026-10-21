---
id: OAG-FOT-001
tipo: metodo
estado: borrador-pendiente-de-aprobacion
fecha: 2026-10-21
sesion: OAG-SES-2026-10-21-01
tags: [OAG, fotometria, landolt, extincion, punto-cero]
---

# OAG-FOT-001 — Modelo fotométrico: punto cero Z y extinción k′

Parte de [[OAG-PLAN-001 Plan del proyecto]]. Los **umbrales numéricos marcados «propuesta»** son puntos de partida para que el usuario los acepte o cambie; no son valores validados.

## 1. Modelo

Para cada filtro $f \in \{U,B,V,R,I\}$ y cada estrella estándar $i$ observada a masa de aire $X$:

$$ m^{\rm inst}_{i} = -2.5\log_{10}\!\left(\frac{F_i}{t_{\rm exp}}\right), \qquad m^{\rm inst}_{i} - M^{\rm Landolt}_{i} = Z_f + k'_f\,X_i \;\;(+\;\epsilon_f\,C_i) $$

- $F_i$: flujo neto en ADU (apertura − cielo), $t_{\rm exp}$ en s.
- $Z_f$: punto cero instrumental (mag, a $X=0$); $k'_f$: coeficiente de extinción de primer orden (mag/masa de aire).
- Término de color $\epsilon_f C_i$ ($C$ = índice de color estándar, p. ej. B−V): **opcional y desactivado por defecto en la v1** (decisión D-09). Sin él, $Z$ y $k'$ dependen de los colores de las estrellas usadas, y el informe debe decirlo.
- Se ajusta por **mínimos cuadrados ponderados**, con *sigma-clipping* iterativo, incertidumbres de $Z$ y $k'$ (covarianza), RMS y número de puntos usados/rechazados.
- Aproximación de primer orden: no se ajusta $k''$ (extinción de segundo orden) en la v1.

## 2. Masa de aire X

- Se calcula **para el instante medio de la exposición** (`DATE-OBS` + `EXPTIME`/2), a partir de la **posición real del campo** (WCS resuelto) y la ubicación del sitio, con una fórmula única y registrada (propuesta: Pickering 2002, la ya usada en el v0.1; ver D-10).
- Se guardan **dos valores**: `AIRMASS` (calculado por el software al capturar, con las coordenadas del puntero) y `OAGAIRM` (recalculado en procesamiento con el WCS). Si difieren más de un umbral (propuesta: 0.02), el reporte lo señala.
- Alerta de captura: masa de aire > propuesta 2.0 → marcar el cuadro, no descartarlo.

## 3. Requisitos de los datos (cobertura)

| Requisito | Motivo | Umbral (propuesta) |
|---|---|---|
| Intervalo de X por filtro | Sin rango de X, k′ no es determinable | ΔX ≥ 0.5 entre extremos (p. ej. 1.1 → 1.6+) |
| Estándares por filtro | Estadística del ajuste | ≥ 10 mediciones independientes, ≥ 3 estrellas distintas |
| Exposiciones repetidas por campo/filtro (N) | Reducir centelleo y ruido | N a definir por el usuario; registrar siempre |
| No saturación ni no-linealidad | Fotometría inválida | pico < propuesta 70 % del rango lineal (a medir; ver D-04) |
| SNR por estrella | Peso y calidad | SNR ≥ propuesta 50 para entrar al ajuste |
| Noche fotométrica | Validez del modelo | RMS de residuos ≤ propuesta 0.03 mag y sin tendencia temporal |

Si un filtro no cumple, el reporte declara **«no calibrable esta noche»** para ese filtro en vez de entregar un valor dudoso.

## 4. Fotometría de apertura (parámetros configurables en `fotometria.yaml`)

- Radio de apertura $r$, anillo de cielo $[r_{\rm in}, r_{\rm out}]$, en **píxeles o en segundos de arco** (esto último exige la escala de placa → depende de D-03).
- Estimador de cielo: mediana con *sigma-clipping* en el anillo; rechazo de píxeles contaminados por vecinas.
- Centroide: recentrado local alrededor de la posición predicha por WCS.
- Opcional: curva de crecimiento y corrección de apertura; la elección del radio queda **documentada en el reporte**.
- Incertidumbre: ruido de Poisson + cielo + lectura + (si se conoce) `EGAIN` y ruido de lectura de la cámara activa. **Ganancia y ruido de lectura deben medirse o tomarse de la hoja del fabricante: PENDIENTE.**

## 5. Lista de campos Landolt (proceso, sin inventar datos)

1. **Consulta** con `astroquery.vizier` a los catálogos de estándares de Landolt. Candidatos a **verificar** (identificadores VizieR exactos por confirmar durante la consulta, no se suponen aquí): Landolt (1992, AJ 104, 340) para estándares ecuatoriales, y Landolt (2009, AJ 137, 4186) / Landolt (2013, AJ 146, 131) para campos adicionales.
2. **Filtro** configurable: declinación visible desde φ ≈ +5.55° (los campos ecuatoriales son favorables), altitud ≥ propuesta 30° durante la ventana prevista, y — cuando se conozca el campo de visión — **al menos *n* estándares dentro del campo** con rango de color amplio y magnitudes compatibles con exposiciones sin saturar.
3. **Salida:** `config/landolt_campos.yaml` con, por campo, identificador, coordenadas, lista de estrellas (magnitudes UBVRI y errores **tal como vienen del catálogo**, con referencia bibliográfica y fecha de consulta) y un campo `estado: borrador | revisado-por-usuario`.
4. **Compuerta:** la secuencia Landolt y el ajuste **rechazan** cualquier campo con `estado: borrador`. Solo el usuario cambia el estado a `revisado-por-usuario`.
5. Estructura del archivo (esqueleto; los valores se llenan desde el catálogo, **no a mano ni de memoria**):

```yaml
campos:
  - id: <PENDIENTE>
    estado: borrador
    fuente: {catalogo: <PENDIENTE>, referencia: <PENDIENTE>, consultado: <PENDIENTE>}
    centro: {ra_deg: <PENDIENTE>, dec_deg: <PENDIENTE>}
    estrellas:
      - {nombre: <PENDIENTE>, ra_deg: <PENDIENTE>, dec_deg: <PENDIENTE>, V: <PENDIENTE>, BV: <PENDIENTE>, UB: <PENDIENTE>, VR: <PENDIENTE>, VI: <PENDIENTE>}
```

## 6. Estrategia de observación para determinar k′ (propuesta a discutir)

- Observar **uno o más campos a distintas masas de aire** durante la noche (al salir y al ponerse), con el ciclo completo de filtros en cada visita, para cubrir ΔX.
- Intercalar campos a X distinto para separar Z de k′; mantener el orden de filtros y los tiempos de exposición registrados.
- El **enfoque** se verifica por filtro; los desplazamientos de enfoque entre filtros (*parfocalidad*) son **PENDIENTES** hasta medirlos.

## 7. Salidas del ajuste

Por filtro: $Z_f \pm \sigma$, $k'_f \pm \sigma$, RMS, N usados/rechazados, intervalo de X cubierto, gráfico $(m^{\rm inst}-M)$ vs $X$ con residuos, tabla de estrellas rechazadas con motivo. Por sesión: informe `.md` con el identificador `OAG-SES-…`, la configuración y versiones de software, el mapa de filtros (con su estado de confirmación) y las advertencias de validez.
