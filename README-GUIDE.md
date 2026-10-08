# Motorcycle route planner

## Setup

Python 3.14 was used during development.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python main.py
```

Open <http://127.0.0.1:5000>. Route calculation is local, but the Leaflet files
and OpenStreetMap tiles need an internet connection.

## Map data

The application requires `data/graph.pkl.gz`. It can be rebuilt from a
Geofabrik `.osm.pbf` extract in `data/kraj-vysocina-latest.osm.pbf` and
SRTM hill data files `.hgt` or `.hgt.gz` files in `data/elevation`:

```bash
python preprocess_osm.py data/kraj-vysocina-latest.osm.pbf --elevation data/elevation
```

The included map boundary is Geofabrik's polygon for [Kraj Vysočina](https://download.geofabrik.de/europe/czech-republic/vysocina.html). The UI masks the rest of the map.

## API

`POST /api/routes` accepts:

```json
{
  "start": {"lat": 49.3961, "lon": 15.5912},
  "target": {"lat": 49.2149, "lon": 15.8817},
  "detour_percent": 35,
  "curve_preference": 70,
  "hill_preference": 45,
  "road_preference": 75,
  "town_preference": 30,
  "avoid_motorways": false
}
```

`POST /api/gpx` accepts a returned `edge_ids` list.

## Benchmark

```bash
python benchmark.py
python benchmark.py --sweep
```

## Project layout

```text
app.py                         flask routes and app factory
main.py                        development entry point
preprocess_osm.py              pbf preprocessing command
benchmark.py                   repeatable regional timings
route_planner/
  graph.py                     graph types, persistence and snapping
  osm_import.py                osm filtering and feature extraction
  router.py                    a* and bounded bi-objective search
  service.py                   validation and response assembly
  gpx.py                       gpx writer
templates/index.html           application page
static/                        map behaviour, boundary and styling
tests/                         integration tests
```
