# Pronóstico de surf – Playa Cerritos, BCS

Proyecto personal que pronostica la **altura** y el **periodo** de las olas para surf en Playa Cerritos
(Baja California Sur), con calificación por hora, viento y marea.

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
- **`data/historial/*.csv`:** cada pronóstico se guarda para que lo compares después con lo que viste.

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

## Observaciones y calibración

Después de cada sesión registra lo que viste; con eso el pronóstico se ajusta a la playa real.

```bash
python observar.py agregar      # pregunta fecha, horas, altura mín/máx, sets, lado, viento, calidad y notas
python observar.py comparar     # tus observaciones vs. lo que pronosticó el modelo
python observar.py calibrar     # guarda el factor sugerido; el siguiente pronóstico ya lo usa
```

- Las observaciones se guardan en `data/observaciones.csv`.
- `comparar` busca en `data/historial/` el último pronóstico emitido **antes** de tu sesión y calcula el
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
