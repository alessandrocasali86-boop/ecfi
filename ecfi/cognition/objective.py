from __future__ import annotations

import numpy as np


def renorm_weights(w: np.ndarray) -> np.ndarray:
    w = np.clip(w, 0.0, None)
    s = np.sum(w, axis=1, keepdims=True)
    s = np.where(s <= 1e-12, 1.0, s)
    return w / s


def update_objective(
    weights: np.ndarray,     # (N,3)
    w_init: np.ndarray,      # (3,)
    b: np.ndarray,           # (N,)
    c: np.ndarray,           # (N,)
    b_max: float,
    c_max: float,
    update_rate: float,
    relax_rate: float,
) -> np.ndarray:
    """
    If (b>b_max) or (c>c_max): shift toward independence (wN up).
    Else: relax slowly back to w_init.
    """
    w = weights.copy()
    triggered = (b > b_max) | (c > c_max)

    if np.any(triggered):
        # increase wN, reduce wI and wC proportionally
        w_tr = w[triggered]
        w_tr[:, 2] = w_tr[:, 2] + update_rate * (1.0 - w_tr[:, 2])
        w_tr[:, 0] = w_tr[:, 0] * (1.0 - update_rate)
        w_tr[:, 1] = w_tr[:, 1] * (1.0 - update_rate)
        w[triggered] = w_tr

    # relax back when not triggered
    if np.any(~triggered):
        w_ok = w[~triggered]
        w_ok = (1.0 - relax_rate) * w_ok + relax_rate * w_init[None, :]
        w[~triggered] = w_ok

    return renorm_weights(w)