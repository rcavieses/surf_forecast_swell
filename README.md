# Pronóstico de surf – Playa Cerritos, BCS

Proyecto personal que pronostica la **altura** y el **periodo** de las olas para surf en Playa Cerritos
(Baja California Sur), con calificación por hora, viento y marea.

**Reporte en línea:** https://rcavieses.github.io/surf_forecast_swell/ (se actualiza solo cada 3 horas).

## Uso

```powershell
pip install -r requirements.txt   # solo la primera vez
python pronostico.py              # o doble clic en pronostico.bat
```

Opciones:

| Opción          | Qué hace                                               |
|-----------------|--------------------------------------------------------|
| `--dias N`      | Días de pronóstico (1-16, por defecto 7)               |
| `--refrescar`   | Ignora la caché (60 min) y descarga datos nuevos       |
| `--no-open`     | No abre el reporte en el navegador                     |

Salidas:
- **Terminal:** resumen diario y tabla de las próximas 48 h.
- **`output/pronostico_cerritos.html`:** reporte interactivo (funciona sin internet una vez generado).
- **`data/historial/*.csv.gz`:** cada pronóstico (próximos 3 días) se guarda para compararlo después con lo que viste.

En el resumen diario:
- **Lado:** hacia dónde abre la ola (izquierda / derecha / pico) según el ángulo del swell con la playa.
  Los bancos de arena del día pueden cambiarlo.
- **Mejores horas:** todas las ventanas con la calificación más alta del día.
- **Confianza:** qué tanto coincide la altura con un segundo modelo de oleaje (GFS de NOAA, línea punteada
  en la gráfica). Alta < 15 % de diferencia, media < 30 %, baja el resto.

## Publicación automática y avisos al teléfono

El workflow [.github/workflows/pronostico.yml](.github/workflows/pronostico.yml) corre cada 3 horas en
GitHub Actions (y cada vez que subes observaciones o cambios al código):

1. Genera el pronóstico y lo publica en GitHub Pages.
2. Guarda el pronóstico en `data/historial/` (haz `git pull` antes de usar `observar.py comparar`).
3. Entre las 18 y 20 h de Cerritos, si en los próximos `ALERT_DAYS` días hay calificación
   ≥ `ALERT_MIN_RATING`, manda un aviso con [ntfy](https://ntfy.sh): instala la app ntfy y suscríbete al
   tema guardado en el secreto `NTFY_TOPIC` del repo. Para probarlo: `NTFY_TOPIC=<tema> python alerta.py --prueba`.

## Cómo funciona

1. **Datos** ([surf_forecast/data.py](surf_forecast/data.py)): descarga de [Open-Meteo](https://open-meteo.com/)
   (gratis, sin API key) el oleaje mar adentro (swell primario, secundario y mar de viento: altura,
   periodo y dirección), el nivel del mar (marea, aproximada) y el viento a 10 m.
2. **Rompiente** ([surf_forecast/surf.py](surf_forecast/surf.py)): por cada componente se calcula la
   altura de rompiente con Komar & Gaughan (1973), `Hb = 0.39·g^0.2·(T·H0²)^0.4`. Después se reduce
   según qué tan de lado llega el swell respecto a la orientación de la playa (SO, 235°); los swells
   fuera de la ventana de exposición se bloquean. Los componentes se combinan por energía.
3. **Calificación (0-5):** según tamaño, periodo y viento (offshore = del NE en Cerritos;
   onshore = del O/SO, que suele entrar por la tarde).
4. **Segundo modelo** ([surf_forecast/data.py](surf_forecast/data.py)): el oleaje de GFS (NOAA) se calcula
   igual para estimar la confianza. ECMWF no tiene datos en este punto de la costa.

## Observaciones y calibración

Después de cada sesión registra lo que viste; con eso el pronóstico se ajusta a la playa real.

**Con interfaz web** (PC o Termux): `python observar_web.py` abre http://localhost:8001 con un formulario para
registrar sesiones, tus sesiones comparadas con el pronóstico (con botón para eliminar), la calibración y un
botón **Sincronizar con GitHub** (commit de `data/`, pull y push). En Termux entra a esa dirección en Chrome y
deja la terminal abierta; se cierra con Ctrl+C.

**Desde la terminal:**

```bash
python observar.py agregar      # pregunta fecha, horas, altura mín/máx, sets, lado, viento, calidad y notas
python observar.py listar       # sesiones registradas, numeradas
python observar.py eliminar 2   # borra la sesión 2 si te equivocaste (pide confirmación)
python observar.py comparar     # tus observaciones vs. lo que pronosticó el modelo
python observar.py calibrar     # guarda el factor sugerido; el siguiente pronóstico ya lo usa
```

- Las observaciones se guardan en `data/observaciones.csv`.
- **Viento** en escala ordinal, comparable con el pronóstico:

  | Nivel | En el agua | Pronóstico |
  |---|---|---|
  | 0 sin viento | glassy, espejo | < 5 km/h |
  | 1 ligero | apenas riza la superficie | 5–12 km/h |
  | 2 moderado | algo de viento, superficie algo picada | 12–20 km/h |
  | 3 fuerte | picado, cuesta remar | 20–30 km/h |
  | 4 muy fuerte | casi imposible surfear | > 30 km/h |

  La **dirección** (de dónde venía: N, NE, E, SE, S, SO, O, NO) se elige en una rosa de los vientos que
  dibuja la playa (mar/tierra) y una flecha cuyo largo indica la fuerza y el color si fue offshore, cruzado u
  onshore. En la terminal: `--viento-dir NE`. Además hay un campo libre para el detalle (a qué hora cambió, etc.).
- `comparar` muestra, por sesión, lo que viste junto a lo pronosticado (altura, lado, viento, calidad) y
  la marea que hubo. También indica si el modelo tiende a sobreestimar o subestimar la calidad.
- Para la altura busca en `data/historial/` el último pronóstico emitido **antes** de tu sesión y calcula el
  `factor_ideal`: el factor de sitio con el que el punto medio del rango pronosticado habría coincidido con
  el punto medio de lo que viste. El factor sugerido es la mediana de todos.
- `calibrar` escribe `data/calibracion.json`, que tiene prioridad sobre `SITE_FACTOR` de `config.py`.
  `calibrar --factor 0.8` fija un valor a mano; `calibrar --reset` vuelve al de `config.py`.
- Con menos de 3 observaciones el factor sugerido es solo orientativo; conviene juntar sesiones con
  swells de distinto tamaño y periodo.
- Como el pronóstico se guarda en el historial cada vez que corres `pronostico.py`, córrelo antes de ir al
  agua para tener con qué comparar.

Otros parámetros del spot en [surf_forecast/config.py](surf_forecast/config.py):

- `SITE_FACTOR`: valor por defecto del factor de sitio si no hay calibración.
- `BEACH_NORMAL_DEG` y `EXPOSURE_HALF_WINDOW_DEG`: orientación de la playa y qué tan amplia es la
  ventana de swell.

## Limitaciones

- El modelo de oleaje tiene una resolución de unos kilómetros; no ve el fondo ni los bancos de arena de la playa.
- La marea viene de un modelo global y es aproximada; para horarios exactos usa una tabla de mareas local.
- Más allá de 5-7 días la precisión baja bastante.
