from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from ecfi.sim.neighbors import torus_dist


@dataclass
class Edge:
    i: int
    j: int
    t_join: int


def _key(i: int, j: int) -> Tuple[int, int]:
    return (i, j) if i < j else (j, i)


def apply_join_detach(
    positions: np.ndarray,
    size: np.ndarray,
    edges: Dict[Tuple[int, int], Edge],
    degrees: np.ndarray,
    t: int,
    Rc: float,
    max_degree: int,
    Tmin: int,
    detach_base_p: float,
    boreness: np.ndarray | None,
    rng: np.random.Generator,
) -> None:
    """
    Mutates edges/degrees in-place.
    - Join if within Rc and both have free degree.
    - Detach after Tmin with probability p = detach_base_p * (1 + b_k + b_l) if boreness provided.
    """
    N = positions.shape[0]

    # JOINS (brute force; ok for MVP N~50)
    for i in range(N):
        if degrees[i] >= max_degree:
            continue
        for j in range(i + 1, N):
            if degrees[j] >= max_degree:
                continue
            k = _key(i, j)
            if k in edges:
                continue
            if torus_dist(positions[i], positions[j], size) < Rc:
                edges[k] = Edge(i=i, j=j, t_join=t)
                degrees[i] += 1
                degrees[j] += 1

    # DETACH
    to_remove: List[Tuple[int, int]] = []
    for k, e in edges.items():
        age = t - e.t_join
        if age < Tmin:
            continue

        p = detach_base_p
        if boreness is not None:
            p = detach_base_p * (1.0 + float(boreness[e.i]) + float(boreness[e.j]))

        if rng.random() < p:
            to_remove.append(k)

    for k in to_remove:
        e = edges.pop(k)
        degrees[e.i] -= 1
        degrees[e.j] -= 1