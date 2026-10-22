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

## Calibración

Todos los parámetros del spot están en [surf_forecast/config.py](surf_forecast/config.py):

- `SITE_FACTOR`: lo más importante. Si el pronóstico te sale alto comparado con lo que ves en el agua,
  bájalo; si sale bajo, súbelo. Usa los CSV de `data/historial/` para comparar.
- `BEACH_NORMAL_DEG` y `EXPOSURE_HALF_WINDOW_DEG`: orientación de la playa y qué tan amplia es la
  ventana de swell.

## Limitaciones

- El modelo de oleaje tiene una resolución de unos kilómetros; no ve el fondo ni los bancos de arena de la playa.
- La marea viene de un modelo global y es aproximada; para horarios exactos usa una tabla de mareas local.
- Más allá de 5-7 días la precisión baja bastante.
