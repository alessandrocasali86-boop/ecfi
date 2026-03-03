from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_dir", type=str, default="outputs/run", help="Directory containing global.csv")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    global_csv = run_dir / "global.csv"
    if not global_csv.exists():
        raise FileNotFoundError(f"Missing {global_csv}")

    df = pd.read_csv(global_csv)

    # coherence
    plt.figure()
    plt.plot(df["t"], df["coherence"])
    plt.xlabel("t")
    plt.ylabel("coherence")
    plt.title("Global phase coherence")
    plt.tight_layout()
    plt.savefig(run_dir / "plot_coherence.png", dpi=160)
    plt.close()

    # clusters
    plt.figure()
    plt.plot(df["t"], df["n_clusters"], label="n_clusters")
    plt.plot(df["t"], df["mean_cluster_size"], label="mean_cluster_size")
    plt.xlabel("t")
    plt.title("Assembly regime indicators")
    plt.legend()
    plt.tight_layout()
    plt.savefig(run_dir / "plot_clusters.png", dpi=160)
    plt.close()

    # intrinsic signals
    plt.figure()
    plt.plot(df["t"], df["mean_novelty"], label="mean_novelty")
    plt.plot(df["t"], df["mean_boreness"], label="mean_boreness")
    plt.plot(df["t"], df["mean_load"], label="mean_load")
    plt.xlabel("t")
    plt.title("Intrinsic signals")
    plt.legend()
    plt.tight_layout()
    plt.savefig(run_dir / "plot_intrinsic.png", dpi=160)
    plt.close()

    print(f"Saved plots to: {run_dir.resolve()}")


if __name__ == "__main__":
    main()