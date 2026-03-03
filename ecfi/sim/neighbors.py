from __future__ import annotations

from typing import List, Tuple

import numpy as np


def torus_delta(a: np.ndarray, b: np.ndarray, size: np.ndarray) -> np.ndarray:
    """Minimum-image displacement on a 2D torus."""
    d = b - a
    d = d - size * np.round(d / size)
    return d


def torus_dist(a: np.ndarray, b: np.ndarray, size: np.ndarray) -> float:
    d = torus_delta(a, b, size)
    return float(np.hypot(d[0], d[1]))


def compute_neighbors_torus(positions: np.ndarray, Rp: float, size: np.ndarray) -> List[List[int]]:
    """
    Brute-force neighbor lists on a torus.
    positions: (N,2)
    returns: neigh[k] = list of neighbor indices within Rp (excluding k)
    """
    N = positions.shape[0]
    neigh: List[List[int]] = [[] for _ in range(N)]
    Rp2 = Rp * Rp
    for i in range(N):
        for j in range(i + 1, N):
            d = torus_delta(positions[i], positions[j], size)
            if float(d[0] * d[0] + d[1] * d[1]) <= Rp2:
                neigh[i].append(j)
                neigh[j].append(i)
    return neigh