# TRACE (lab notebook)

This file is a chronological log of experiments, decisions, and results.
Keep entries short, dated, and reproducible (config, seed, command, outputs).

---

## 2026-03-02
### Repo reset + publication
- Goal: restart from baseline skeleton on `main`, preserve full history on `archive`.
- Actions:
  - `archive` branch kept at snapshot commit `bf09f99`.
  - `main` reset to initial skeleton commit `5b99bc5`.
  - Remote set to GitHub and pushed `main`, `archive`, and tag `archive-2026-03-02`.

### Conventions (from now on)
- Development happens on feature branches (or `dev`), merged into `main` only for releases.
- Every release:
  1) update `CHANGELOG.md`
  2) tag `vX.Y.Z`
  3) GitHub Release notes copied from changelog

---

## 2026-03-03
### Baseline freeze (H) + H1 regime-switch artifacts
- Context: freeze the first runnable prototype and the baseline diagnostic cycle (H), then capture the first regime-switch tuning run (H1).
- Baseline (H):
  - Run: `python -m ecfi.run --config configs/base.yaml --seed 0`
  - Plots: `python -m ecfi.viz.plot_run --run_dir outputs/run`
  - Frozen report: `docs/ecfi_minipaper_trace.tex` + `docs/figures/plot_{clusters,coherence,intrinsic}.png`
  - Expected behavior: rapid collapse to a single assembly component and near-permanent phase lock-in.
- H1 (regime-switch):
  - Run: `python -m ecfi.run --config configs/regime_switch.yaml --seed 0`
  - Plots: `python -m ecfi.viz.plot_run --run_dir outputs/run`
  - Frozen artifacts:
    - Figures: `docs/figures/h1_regime_switch_seed0/plot_{clusters,coherence,intrinsic}.png`
    - Run metadata: `docs/runs/h1_regime_switch_seed0_{config_resolved.json,global.csv}`
  - Observed behavior: nontrivial cluster dynamics (no permanent single cluster) and coherence trajectories that do not remain locked at 1.
- Releases:
  - v0.1.1: first runnable prototype + baseline report (H).
  - v0.1.2: H1 regime-switch artifacts merged into main.

## Template for new entries

## YYYY-MM-DD
### Topic / experiment title
- Context:
- Hypothesis:
- Config / command:
- Seed(s):
- Key results:
- Files changed:
- Next:
