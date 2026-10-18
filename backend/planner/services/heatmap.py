"""Weather grid along the trip corridor for every hour from departure to +48 h.

The grid is regular in Web Mercator (so the frontend can drape it over the map
as a single image without distortion). Only cells within the corridor around
the routes are fetched, which keeps the forecast request small; the frontend
interpolates between cell centres to draw a smooth heatmap.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..domain.geo import LatLon, Polyline, inverse_mercator_y, mercator_y, min_distance_mi
from ..domain.risk import assess
from .weather import fetch_hourly, hour_floor

HOURS = 48
MAX_FETCH_CELLS = 200
TARGET_GRID_CELLS = 700
MI_PER_RADIAN = 3958.7613


def build_heatmap(corridors: list[list[LatLon]], departure: datetime, load_lb: float) -> dict:
    pts = [p for c in corridors for p in c]
    lat_min, lat_max = min(p[0] for p in pts), max(p[0] for p in pts)
    lon_min, lon_max = min(p[1] for p in pts), max(p[1] for p in pts)
    pad = max(0.4, 0.08 * max(lat_max - lat_min, lon_max - lon_min))
    lat_min, lat_max, lon_min, lon_max = lat_min - pad, lat_max + pad, lon_min - pad, lon_max + pad

    # Mercator extents in radians.
    x0, x1 = math.radians(lon_min), math.radians(lon_max)
    y0, y1 = mercator_y(lat_min), mercator_y(lat_max)
    cell = math.sqrt((x1 - x0) * (y1 - y0) / TARGET_GRID_CELLS)

    lines = [Polyline(c) for c in corridors if len(c) >= 2]
    while True:
        nx, ny = max(2, math.ceil((x1 - x0) / cell)), max(2, math.ceil((y1 - y0) / cell))
        centers = [
            (inverse_mercator_y(y1 - (r + 0.5) * cell), math.degrees(x0 + (c + 0.5) * cell))
            for r in range(ny)
            for c in range(nx)
        ]
        # Ground size of a cell at the corridor's mean latitude.
        cell_mi = cell * MI_PER_RADIAN * math.cos(math.radians((lat_min + lat_max) / 2))
        radius = max(35.0, 1.6 * cell_mi)
        samples = [p for line in lines for p in line.sample_every(max(cell_mi / 3, 2.0))]
        cells = [i for i, ctr in enumerate(centers) if min_distance_mi(ctr, samples) <= radius]
        if len(cells) <= MAX_FETCH_CELLS:
            break
        cell *= 1.15

    # Hourly frames from the hour containing departure through departure + 48 h
    # (one extra frame because departure is usually mid-hour).
    start = hour_floor(departure)
    frames = HOURS + 1 if start == departure else HOURS + 2
    series = fetch_hourly([centers[i] for i in cells], start, start + timedelta(hours=frames - 1))

    times = [int((start + timedelta(hours=h)).timestamp()) for h in range(frames)]
    layers: dict[str, list[list[float]]] = {"risk": [], "wind": [], "gust": [], "rain": [], "snow": []}
    for t in times:
        moment = datetime.fromtimestamp(t, tz=start.tzinfo)
        frame = {k: [] for k in layers}
        for s in series:
            w = s.sample(moment)
            frame["wind"].append(w["wind_mph"])
            frame["gust"].append(w["gust_mph"])
            frame["rain"].append(w["rain_in_hr"])
            frame["snow"].append(w["snow_in_hr"])
            frame["risk"].append(int(assess(w["wind_mph"], w["rain_in_hr"], w["snow_in_hr"], load_lb).level))
        for k in layers:
            layers[k].append(frame[k])

    return {
        "bounds": {
            "west": math.degrees(x0),
            "east": math.degrees(x0 + nx * cell),
            "north": inverse_mercator_y(y1),
            "south": inverse_mercator_y(y1 - ny * cell),
        },
        "nx": nx,
        "ny": ny,
        "cells": cells,  # row-major indices (row 0 = north) of cells that carry data
        "times": times,
        "layers": layers,  # layers[name][hour][k] is the value for cells[k]
    }
