# E-CFI Demo — Development Trace (G → H → H′)

This file is a lightweight chronological log of the engineering steps used to build the minimal E-CFI demo prototype,
together with the first diagnostic cycle and the subsequent tuning plan (Step H′).  
It is meant to be short, actionable, and reproducible.

---

## Repository
- Repo name: `ecfi`
- Main entrypoint: `python -m ecfi.run --config <yaml> --seed <int>`
- Outputs (default): `outputs/run/` containing at least:
  - `global.csv`, `agents.csv`
  - `config_resolved.json` (if enabled)
  - diagnostic plots (PNG)

---

## Milestone G — Oscillators + assembly merges + coherence logging
**Goal:** introduce embodied self-assembly dynamics and event-driven oscillators; expose coherence as a global signature.

### Implemented
- Assembly graph `G_A(t)` via join/detach (slot-limited edges)
- Connected components → cluster ids and cluster size statistics
- Per-agent oscillator phase `phase ∈ [0,1)`, with free-running drift
- Merge-triggered phase synchronization (initially “hard sync”)
- Logs:
  - per-agent: `phase`, `degree`, `cluster_id`
  - global: `coherence`, `n_clusters`, `mean_cluster_size`, `n_edges`

### Commands (baseline)
```bash
python -m ecfi.run --config configs/base.yaml --seed 0