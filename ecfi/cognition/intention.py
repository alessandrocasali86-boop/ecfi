from __future__ import annotations

from typing import Tuple

import numpy as np


def update_intention(
    omega: np.ndarray,         # (N,d)
    x: np.ndarray,             # (N,d)
    neigh_sum_x: np.ndarray,   # (N,d)
    beta_eff: np.ndarray,      # (N,)
    alpha: float,
    tau_c: float,
    g: float,
    dt: float,
    clip_norm: float = 5.0,
) -> np.ndarray:
    """
    Discrete update of a CFI-like intention dynamics:
      dω/dt = α x + β_eff * sum_{ℓ in Neigh} x_ℓ - g ||ω||^2 ω
    """
    norm2 = np.sum(omega * omega, axis=1, keepdims=True)  # (N,1)
    domega = alpha * x + beta_eff[:, None] * neigh_sum_x - g * norm2 * omega
    omega = omega + (dt / tau_c) * domega

    # safety clip
    norms = np.linalg.norm(omega, axis=1)
    scale = np.ones_like(norms)
    mask = norms > clip_norm
    scale[mask] = clip_norm / (norms[mask] + 1e-12)
    omega = omega * scale[:, None]
    return omega


def beta_effective(weights: np.ndarray, beta_I: float, beta_C: float, beta_N: float) -> np.ndarray:
    """
    weights: (N,3) columns [wI,wC,wN]
    returns beta_eff: (N,)
    """
    return (
        weights[:, 0] * beta_I
        + weights[:, 1] * beta_C
        + weights[:, 2] * beta_N
    )