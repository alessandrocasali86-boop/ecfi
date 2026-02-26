from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict

import numpy as np
import matplotlib.pyplot as plt


def read_global_csv(path: Path) -> Dict[str, np.ndarray]:
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)

    def col(name: str, default: float = 0.0) -> np.ndarray:
        if not rows or name not in rows[0]:
            return np.array([default] * len(rows), dtype=float)
        return np.array([float(row.get(name, default) or default) for row in rows], dtype=float)

    return {
        "t": col("t"),
        "coherence": col("coherence"),
        "n_clusters": col("n_clusters"),
        "mean_cluster_size": col("mean_cluster_size"),
        "mean_novelty": col("mean_novelty"),
        "mean_boreness": col("mean_boreness"),
        "mean_load": col("mean_load"),
        "n_joined": col("n_joined", 0.0),
        "n_detached": col("n_detached", 0.0),
        "n_merges": col("n_merges", 0.0),
        "mean_omega0": col("mean_omega0", np.nan),
        "std_omega0": col("std_omega0", np.nan),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_dir", type=str, default="outputs/run")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    gpath = run_dir / "global.csv"
    if not gpath.exists():
        raise FileNotFoundError(f"Missing {gpath}")

    d = read_global_csv(gpath)
    t = d["t"]
    merge_ts = t[d["n_merges"] > 0.0]

    # 1) Assembly indicators + merge markers
    plt.figure()
    plt.title("Assembly indicators + merge markers")
    plt.plot(t, d["n_clusters"], label="n_clusters")
    plt.plot(t, d["mean_cluster_size"], label="mean_cluster_size")
    for tt in merge_ts:
        plt.axvline(tt, alpha=0.15)
    plt.xlabel("t")
    plt.legend()
    plt.tight_layout()
    plt.savefig(run_dir / "plot_events_assembly.png", dpi=150)
    plt.close()

    # 2) Coherence + merge markers
    plt.figure()
    plt.title("Global phase coherence + merge markers")
    plt.plot(t, d["coherence"], label="coherence")
    for tt in merge_ts:
        plt.axvline(tt, alpha=0.15)
    plt.xlabel("t")
    plt.legend()
    plt.tight_layout()
    plt.savefig(run_dir / "plot_events_coherence.png", dpi=150)
    plt.close()

    # 3) Event counts
    plt.figure()
    plt.title("Join/detach/merge events (per step)")
    plt.plot(t, d["n_joined"], label="n_joined")
    plt.plot(t, d["n_detached"], label="n_detached")
    plt.plot(t, d["n_merges"], label="n_merges")
    plt.xlabel("t")
    plt.legend()
    plt.tight_layout()
    plt.savefig(run_dir / "plot_events_counts.png", dpi=150)
    plt.close()

    # 4) Intrinsic signals
    plt.figure()
    plt.title("Intrinsic signals")
    plt.plot(t, d["mean_novelty"], label="mean_novelty")
    plt.plot(t, d["mean_boreness"], label="mean_boreness")
    plt.plot(t, d["mean_load"], label="mean_load")
    plt.xlabel("t")
    plt.legend()
    plt.tight_layout()
    plt.savefig(run_dir / "plot_events_intrinsic.png", dpi=150)
    plt.close()

    print(f"Saved event-aware plots to: {run_dir}")


if __name__ == "__main__":
    main()