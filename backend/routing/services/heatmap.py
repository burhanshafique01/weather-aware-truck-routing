"""Grid of forecast cells covering the corridor around all candidate routes.

The grid is regular in latitude/longitude so the frontend can draw it as
rectangles that tile without gaps. Cell size scales with trip length and is
coarsened until the cell count fits the budget, which bounds both weather API
usage and the browser's rendering work.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from . import geo

MAX_CELLS = 220
MIN_CELL_MI = 6.0
MAX_CELL_MI = 40.0
MILES_PER_DEG_LAT = 69.0


@dataclass(frozen=True)
class Grid:
    dlat: float
    dlon: float
    cells: list[geo.LatLon]  # cell centres


def corridor_grid(routes: Sequence[tuple[Sequence[geo.LatLon], Sequence[float]]], max_cells: int = MAX_CELLS) -> Grid:
    """Cells within one cell of any route. ``routes`` is (coords, cum_mi) pairs."""
    longest = max(cum[-1] for _, cum in routes)
    mean_lat = sum(c[0][0] + c[-1][0] for c, _ in routes) / (2 * len(routes))
    cell_mi = min(max(longest / 30, MIN_CELL_MI), MAX_CELL_MI)

    while True:
        dlat = cell_mi / MILES_PER_DEG_LAT
        dlon = cell_mi / (MILES_PER_DEG_LAT * max(math.cos(math.radians(mean_lat)), 0.2))
        indices: set[tuple[int, int]] = set()
        for coords, cum in routes:
            for d in geo.sample_distances(cum[-1], cell_mi / 2):
                (lat, lon), _, _ = geo.interpolate_along(coords, cum, d)
                i, j = math.floor(lat / dlat), math.floor(lon / dlon)
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        indices.add((i + di, j + dj))
        if len(indices) <= max_cells or cell_mi >= MAX_CELL_MI * 2:
            break
        cell_mi *= 1.2

    cells = [((i + 0.5) * dlat, (j + 0.5) * dlon) for i, j in sorted(indices)]
    return Grid(dlat=dlat, dlon=dlon, cells=cells)
