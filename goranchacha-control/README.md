# Goranchacha Control

Sistema de control del **Observatorio Astronómico Goranchacha (UPTC)**: un **servidor** que corre en el PC del
observatorio (habla con los equipos por ASCOM/Alpaca) y una **aplicación de escritorio** (PySide6) que se conecta
al servidor, ya sea en el mismo PC o de forma remota.

```
 App de escritorio ──HTTPS/token──▶ Servidor (FastAPI) ──▶ Observatory (núcleo)
 (PC, local o remoto)                   │                      ├─ Seguridad meteorológica + cierre automático
                                        │                      ├─ Secuenciador / planificador
                                        │                      └─ Dispositivos: simulador | ASCOM Alpaca
                                        └─ Bitácora + usuarios (SQLite) · imágenes FITS
```

## Qué incluye (v0.1)

| Módulo | Estado |
|---|---|
| Montura, cámara, filtros, enfocador, domo/obturador, estación meteorológica | Interfaces + simuladores + cliente Alpaca |
| Seguridad: viento, ráfagas, humedad, punto de rocío, nubes, lluvia, lectura obsoleta, fallo del sensor (fail-safe) | Sí, con cierre de emergencia automático |
| Domo esclavizado a la montura | Sí |
| Autoenfoque (barrido V-curve, ajuste parabólico) | Sí |
| Secuencias: prioridades, altitud mínima, ventanas horarias, espera de noche astronómica, calibraciones (bias/dark) | Sí |
| FITS con cabeceras científicas (DATE-OBS, EXPTIME, FILTER, RA/DEC, CCD-TEMP, AIRMASS, sitio…) | Sí, una carpeta por noche |
| Usuarios con roles `viewer` / `operator` / `admin`, auditoría en bitácora | Sí |
| Acceso remoto | HTTPS + token firmado; el servidor se niega a escuchar en red sin TLS |

## Instalación

```bash
cd goranchacha-control
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[gui,dev]"
cp config/observatorio.example.yaml observatorio.yaml   # editar
goranchacha-user ADMIN admin --config observatorio.yaml # crea el primer usuario
goranchacha-server --config observatorio.yaml           # en el PC del observatorio
goranchacha-gui                                         # en el PC del operador
pytest                                                  # 33 pruebas
```

Por defecto usa **simuladores**, así que se puede probar todo sin hardware.

## Pasar a equipos reales (ASCOM)

1. En el PC del observatorio (Windows) instale los drivers ASCOM de cada equipo y **ASCOM Remote / Alpaca**
   (o use dispositivos con Alpaca nativo).
2. En `observatorio.yaml`: `devices.backend: alpaca` y complete un bloque por equipo (URL y número de dispositivo).
3. **Antes de operar con equipos reales**, pruebe cada equipo por separado con el telescopio libre y el domo vacío,
   y verifique el cierre de emergencia en seco.

## Acceso remoto

- Para escuchar en la red, configure `server.host: 0.0.0.0` **y** `ssl_certfile`/`ssl_keyfile`.
  Preferible: dejar el servidor en `127.0.0.1` y publicarlo solo por **VPN** (WireGuard/Tailscale) o un proxy TLS.
- No exponga el puerto directamente a internet. Las contraseñas exigen ≥ 10 caracteres y hay bloqueo por intentos.
- El secreto de firma de tokens se genera en `data_dir/secreto.key`; protéjalo y no lo versione.

## Seguridad del observatorio (leer)

- Sin lecturas meteorológicas válidas el sistema se considera **inseguro**.
- Ante condiciones inseguras: se detiene la secuencia, se aborta la exposición, se estaciona la montura y se cierra
  el obturador. La **reapertura es siempre manual** y exige `safe_hold_minutes` de condiciones estables y el Sol
  bajo `sun_altitude_open_limit_deg`.
- **El software no sustituye la protección en hardware.** El observatorio debe tener un sensor de lluvia que cierre
  el techo por cableado/PLC e independiente del PC, y SAI (UPS) para completar un cierre si se corta la luz.

## Limitaciones conocidas / próximos pasos

- Las coordenadas se tratan tal como las reporta el driver (sin conversión J2000↔JNow).
- Imagen por Alpaca vía JSON (`imagearray`): correcto pero lento en sensores grandes; falta `ImageBytes` binario.
- Sin guiado (PHD2), plate solving, flats automáticos, ni fotometría en línea todavía.
- No hay vista previa de imagen en la GUI; los FITS se guardan en el servidor.
- La secuencia no se reanuda sola tras cerrarse por clima.
- Las coordenadas del sitio en la configuración son aproximadas: **verifíquelas**.
