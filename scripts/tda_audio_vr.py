from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import librosa
import matplotlib.pyplot as plt
from ripser import ripser
from persim import wasserstein, plot_diagrams


AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}


def finite_dgm(dgm: np.ndarray) -> np.ndarray:
    if dgm is None or getattr(dgm, "size", 0) == 0:
        return np.empty((0, 2), dtype=float)
    dgm = np.asarray(dgm, dtype=float)
    if dgm.ndim != 2 or dgm.shape[1] < 2:
        return np.empty((0, 2), dtype=float)
    mask = np.isfinite(dgm[:, 0]) & np.isfinite(dgm[:, 1])
    return dgm[mask][:, :2]


def list_audio_files(audio_dir: Path, prefer_ext: str = "wav") -> List[Path]:
    prefer = "." + prefer_ext.lower().lstrip(".")
    candidates = [p for p in audio_dir.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS]
    by_stem: Dict[str, List[Path]] = {}
    for p in candidates:
        by_stem.setdefault(p.stem, []).append(p)

    chosen: List[Path] = []
    for stem, ps in sorted(by_stem.items(), key=lambda kv: kv[0]):
        ps_sorted = sorted(ps, key=lambda x: x.suffix.lower())
        pref = [p for p in ps_sorted if p.suffix.lower() == prefer]
        chosen.append(pref[0] if pref else ps_sorted[0])
    return chosen


def load_audio(path: Path, sr: int, duration: float | None = None) -> Tuple[np.ndarray, int]:
    y, sr2 = librosa.load(str(path), sr=sr, mono=True, duration=duration)
    y = np.asarray(y, dtype=np.float32)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    return y, sr2


def mel_frames_db(
    y: np.ndarray,
    sr: int,
    n_fft: int,
    hop_length: int,
    n_mels: int,
    fmin: float = 30.0,
    fmax: float | None = None,
) -> np.ndarray:
    S = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=n_fft, hop_length=hop_length,
        n_mels=n_mels, fmin=fmin, fmax=fmax
    )
    S_db = librosa.power_to_db(S, ref=np.max)
    S_db = np.nan_to_num(S_db, nan=-120.0, posinf=0.0, neginf=-120.0)
    S_db = np.clip(S_db, -120.0, 0.0)
    return S_db.T  # (frames, n_mels)


def sample_frames(X: np.ndarray, max_frames: int, mode: str, seed: int) -> np.ndarray:
    n = X.shape[0]
    if n <= max_frames:
        return X

    rng = np.random.default_rng(seed)

    if mode == "uniform":
        idx = np.linspace(0, n - 1, max_frames).astype(int)
        return X[idx]
    if mode == "random":
        idx = rng.choice(n, size=max_frames, replace=False)
        idx.sort()
        return X[idx]
    if mode == "head":
        return X[:max_frames]
    if mode == "tail":
        return X[-max_frames:]

    raise ValueError(f"Unknown frame_sampling='{mode}' (use uniform|random|head|tail)")


def zscore_clip(X: np.ndarray, clip: float = 6.0) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    mu = X.mean(axis=0, keepdims=True)
    sig = X.std(axis=0, keepdims=True)
    sig = np.where(sig < 1e-10, 1.0, sig)

    Z = (X - mu) / sig
    Z = np.clip(Z, -clip, clip)
    Z = np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)
    return Z.astype(np.float32)


def pca_svd(X: np.ndarray, k: int) -> np.ndarray:
    """
    PCA via SVD (no sklearn). Returns (n, k).
    Robust: float64, sanitize before/after, suppress BLAS RuntimeWarnings locally.
    """
    X = np.asarray(X, dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    n, d = X.shape
    if k <= 0 or k >= d:
        return X.astype(np.float32)

    Xc = X - X.mean(axis=0, keepdims=True)
    Xc = np.nan_to_num(Xc, nan=0.0, posinf=0.0, neginf=0.0)

    with np.errstate(all="ignore"):
        _, _, Vt = np.linalg.svd(Xc, full_matrices=False)

    V = np.asarray(Vt[:k, :].T, dtype=np.float64)  # (d, k)
    V = np.nan_to_num(V, nan=0.0, posinf=0.0, neginf=0.0)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*encountered in matmul.*")
        with np.errstate(all="ignore"):
            Z = Xc @ V

    Z = np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)
    return Z.astype(np.float32)


def pairwise_distances_euclidean(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    diff = X[:, None, :] - X[None, :, :]
    D2 = np.sum(diff * diff, axis=-1, dtype=np.float32)
    D2 = np.maximum(D2, 0.0)
    D = np.sqrt(D2).astype(np.float32)
    np.fill_diagonal(D, 0.0)
    return D


def auto_thresh_from_D(D: np.ndarray, q: float) -> float:
    tri = D[np.triu_indices(D.shape[0], k=1)]
    tri = tri[np.isfinite(tri)]
    tri = tri[tri > 0]
    if tri.size == 0:
        return 1.0
    return float(np.quantile(tri, q))


def compute_vr_from_distance(D: np.ndarray, maxdim: int, thresh: float) -> List[np.ndarray]:
    out = ripser(D, distance_matrix=True, maxdim=maxdim, thresh=float(thresh))
    return out["dgms"]


def save_plot_overlay(dgms: List[np.ndarray], out_png: Path, title: str) -> None:
    plt.figure(figsize=(7, 5))
    plot_diagrams(dgms, show=False)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def save_plot_split(dgms: List[np.ndarray], out_png: Path, title: str, maxdim: int) -> None:
    cols = maxdim + 1
    plt.figure(figsize=(5 * cols, 4))
    for dim in range(cols):
        ax = plt.subplot(1, cols, dim + 1)
        dgm = np.asarray(dgms[dim], dtype=float) if dim < len(dgms) else np.empty((0, 2))
        dgm = finite_dgm(dgm)
        if dgm.size > 0:
            ax.scatter(dgm[:, 0], dgm[:, 1], s=18)
            lo = float(np.min(dgm))
            hi = float(np.max(dgm))
        else:
            lo, hi = 0.0, 1.0
        ax.plot([lo, hi], [lo, hi])
        ax.set_title(f"H{dim}")
        ax.set_xlabel("birth")
        ax.set_ylabel("death")
    plt.suptitle(title)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def wasserstein_compat(dgm1: np.ndarray, dgm2: np.ndarray, p: int) -> float:
    """
    persim.wasserstein signature differs across versions (p vs order).
    We adapt at runtime and suppress backend matmul RuntimeWarnings (sklearn/extmath).
    """
    import inspect
    sig = inspect.signature(wasserstein)
    kwargs = {"matching": False}
    if "p" in sig.parameters:
        kwargs["p"] = p
    elif "order" in sig.parameters:
        kwargs["order"] = p

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*encountered in matmul.*")
        with np.errstate(all="ignore"):
            return float(wasserstein(dgm1, dgm2, **kwargs))


@dataclass
class RunConfig:
    audio_dir: str
    out_dir: str
    sr: int
    duration: Optional[float]
    n_mels: int
    n_fft: int
    hop_length: int
    max_frames: int
    frame_sampling: str
    seed: int
    pca_dim: int
    maxdim: int
    thresh: float
    thresh_mode: str
    thresh_quantile: float
    wasserstein_p: int
    plot_mode: str
    prefer_ext: str


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio_dir", type=str, default="audio")
    ap.add_argument("--out_dir", type=str, default="audio_tda_out_nowarn")

    ap.add_argument("--sr", type=int, default=22050)
    ap.add_argument("--duration", type=float, default=-1.0, help="<=0 means full file")

    ap.add_argument("--n_mels", type=int, default=40)
    ap.add_argument("--n_fft", type=int, default=2048)
    ap.add_argument("--hop_length", type=int, default=512)

    ap.add_argument("--max_frames", type=int, default=400)
    ap.add_argument("--frame_sampling", type=str, default="uniform", choices=["uniform", "random", "head", "tail"])
    ap.add_argument("--seed", type=int, default=0)

    ap.add_argument("--pca_dim", type=int, default=8)
    ap.add_argument("--maxdim", type=int, default=2)

    ap.add_argument("--thresh", type=float, default=-1.0, help="<=0 means auto")
    ap.add_argument("--thresh_mode", type=str, default="global", choices=["global", "per_file"])
    ap.add_argument("--thresh_quantile", type=float, default=0.90)

    ap.add_argument("--wasserstein_p", type=int, default=1)

    ap.add_argument("--plot_mode", type=str, default="both", choices=["overlay", "split", "both", "none"])
    ap.add_argument("--prefer_ext", type=str, default="wav")

    args = ap.parse_args()

    audio_dir = Path(args.audio_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    duration = None if args.duration <= 0 else float(args.duration)

    files = list_audio_files(audio_dir, prefer_ext=args.prefer_ext)
    if not files:
        print(f"No audio files found in: {audio_dir.resolve()}", file=sys.stderr)
        sys.exit(2)

    clouds: Dict[str, np.ndarray] = {}
    Ds: Dict[str, np.ndarray] = {}
    auto_ths: Dict[str, float] = {}

    for p in files:
        name = p.stem
        print(f"\nProcessing: {p.name}")
        y, sr = load_audio(p, sr=args.sr, duration=duration)

        X = mel_frames_db(
            y, sr,
            n_fft=args.n_fft,
            hop_length=args.hop_length,
            n_mels=args.n_mels,
        )
        X = sample_frames(X, max_frames=args.max_frames, mode=args.frame_sampling, seed=args.seed)
        Z = zscore_clip(X, clip=6.0)
        Z = pca_svd(Z, k=args.pca_dim)

        clouds[name] = Z
        D = pairwise_distances_euclidean(Z)
        Ds[name] = D
        auto_ths[name] = auto_thresh_from_D(D, q=float(args.thresh_quantile))

    if args.thresh > 0:
        thresh = float(args.thresh)
    else:
        if args.thresh_mode == "per_file":
            thresh = float("nan")
        else:
            vals = np.array(list(auto_ths.values()), dtype=float)
            thresh = float(np.median(vals))

    dgms_by_name: Dict[str, List[np.ndarray]] = {}
    for name in sorted(clouds.keys()):
        D = Ds[name]
        th = auto_ths[name] if (args.thresh <= 0 and args.thresh_mode == "per_file") else thresh
        dgms = compute_vr_from_distance(D, maxdim=args.maxdim, thresh=th)
        dgms_by_name[name] = dgms

        title = f"{name} | VR on log-mel frames (PCA={args.pca_dim}, frames={args.max_frames})"
        if args.plot_mode in ("overlay", "both"):
            save_plot_overlay(dgms, out_dir / f"{name}_vr_diagrams.png", title=title)
        if args.plot_mode in ("split", "both"):
            save_plot_split(dgms, out_dir / f"{name}_vr_diagrams_split.png", title=title, maxdim=args.maxdim)

    names = sorted(dgms_by_name.keys())
    rows = []
    for dim in range(args.maxdim + 1):
        print(f"\nWasserstein distances (H{dim}, p={args.wasserstein_p}):")
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a_name, b_name = names[i], names[j]
                a = finite_dgm(dgms_by_name[a_name][dim])
                b = finite_dgm(dgms_by_name[b_name][dim])
                d = wasserstein_compat(a, b, p=int(args.wasserstein_p))
                print(f"  {a_name} vs {b_name} : {d:.4f}")
                rows.append({
                    "homology_dim": dim,
                    "a": a_name,
                    "b": b_name,
                    "wasserstein": d,
                    "p": int(args.wasserstein_p),
                    "max_frames": int(args.max_frames),
                    "pca_dim": int(args.pca_dim),
                    "frame_sampling": args.frame_sampling,
                    "thresh_mode": args.thresh_mode,
                    "thresh_quantile": float(args.thresh_quantile),
                    "thresh_used": (auto_ths[a_name] if (args.thresh <= 0 and args.thresh_mode == "per_file") else thresh),
                })

    csv_path = out_dir / "wasserstein_distances.csv"
    if rows:
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    cfg = RunConfig(
        audio_dir=str(audio_dir),
        out_dir=str(out_dir),
        sr=int(args.sr),
        duration=duration,
        n_mels=int(args.n_mels),
        n_fft=int(args.n_fft),
        hop_length=int(args.hop_length),
        max_frames=int(args.max_frames),
        frame_sampling=str(args.frame_sampling),
        seed=int(args.seed),
        pca_dim=int(args.pca_dim),
        maxdim=int(args.maxdim),
        thresh=float(args.thresh),
        thresh_mode=str(args.thresh_mode),
        thresh_quantile=float(args.thresh_quantile),
        wasserstein_p=int(args.wasserstein_p),
        plot_mode=str(args.plot_mode),
        prefer_ext=str(args.prefer_ext),
    )
    meta = {
        "config": asdict(cfg),
        "versions": {
            "python": sys.version,
            "numpy": np.__version__,
            "librosa": getattr(librosa, "__version__", "unknown"),
        },
    }
    (out_dir / "run_config.json").write_text(json.dumps(meta, indent=2))

    print(f"\nSaved diagram plots in: {out_dir.resolve()}")
    print(f"Saved distances CSV in: {csv_path.resolve()}")


if __name__ == "__main__":
    main()
