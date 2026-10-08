# Motorcycle route planner

A local route planner for motorcycle rides in Kraj Vysočina. It finds the
fastest route, then looks for alternatives that suit the selected preferences
without exceeding the maximum detour. Routes can be downloaded as GPX files.

## Setup

Run these commands from the `implementation` folder.

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
SRTM elevation files (`.hgt` or `.hgt.gz`) in `data/elevation`:

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

These commands measure route searches between three pairs of towns. The
`--sweep` option also compares different detour limits.

```bash
python benchmark.py
python benchmark.py --sweep
```

## Project layout

```text
app.py                         Flask endpoints
main.py                        development entry point
preprocess_osm.py              builds the road graph from OSM data
benchmark.py                   measures route search times
route_planner/
  graph.py                     road nodes, edges, saving and point snapping
  osm_import.py                reads roads and calculates their scores
  router.py                    A* and route search with time and penalty labels
  service.py                   checks requests and prepares route results
  geo.py                       distances and bearings
  elevation.py                 reads heights from elevation tiles
  gpx.py                       creates GPX downloads
templates/index.html           application page
static/                        map behaviour, boundary and styling
tests/                         automated tests
```
