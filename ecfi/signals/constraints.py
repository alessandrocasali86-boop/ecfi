from __future__ import annotations

import numpy as np


def ema_update(prev: np.ndarray, cur: np.ndarray, rate: float) -> np.ndarray:
    return (1.0 - rate) * prev + rate * cur


def novelty_from_F(F_prev: np.ndarray, F_new: np.ndarray) -> np.ndarray:
    return np.linalg.norm(F_new - F_prev, axis=1)


def update_boreness(b_prev: np.ndarray, novelty: np.ndarray, lam: float, eta: float) -> np.ndarray:
    """
    b(t) = (1-lam)b(t-1) + lam * max(0, eta - novelty)
    """
    return (1.0 - lam) * b_prev + lam * np.maximum(0.0, eta - novelty)


def update_event_rate(er_prev: np.ndarray, events: np.ndarray, rate: float) -> np.ndarray:
    return (1.0 - rate) * er_prev + rate * events


def compute_load(
    neigh_sizes: np.ndarray,
    degrees: np.ndarray,
    event_rate: np.ndarray,
    novelty: np.ndarray,
    gamma: np.ndarray,
) -> np.ndarray:
    """
    c = γ1*|Neigh| + γ2*deg + γ3*event_rate + γ4*novelty
    """
    return (
        gamma[0] * neigh_sizes
        + gamma[1] * degrees.astype(float)
        + gamma[2] * event_rate
        + gamma[3] * novelty
    )