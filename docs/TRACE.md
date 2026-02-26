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

## Diagnostic Cycle (H′ config) — regime_switch.yaml

- Config: `configs/regime_switch.yaml`
- Seed: `0`
- Outputs: `outputs/run/` (global.csv, agents.csv, plots)
- Figures (archived):
  - `docs/figures/plot_clusters_Hprime_seed0.png`
  - `docs/figures/plot_coherence_Hprime_seed0.png`
  - `docs/figures/plot_intrinsic_Hprime_seed0.png`

### Observations
- Assembly dynamics no longer collapses into a single component:
  `n_clusters(t)` spans a wide range (fragmentation/coalescence phases) and `mean_cluster_size(t)` stays mostly low.
- Global phase coherence still saturates to 1 early and remains locked throughout the run.
- Novelty exhibits recurrent spikes (early and late), while load varies smoothly with interaction intensity.
  Boreness remains visually small at the current plot scale (expected given the update rule tends to O(η) when novelty is low).

### Interpretation
- Step H′ successfully induces regime switching in the assembly layer (contact graph topology).
- Coherence is currently an absorbing indicator: once phases become identical under deterministic identical oscillators,
  they remain identical even if the population later detaches into multiple components.
  Therefore, coherence does not track assembly reconfigurations unless symmetry is broken.

### Action items (next step)
- Implement Step H′′ oscillator fix:
  (i) replace hard merge-sync with soft sync, and (ii) add small phase noise or per-agent ω0 heterogeneity,
  so that coherence can decrease after detachments and become regime-sensitive.
- Improve diagnostics: add a dedicated plot for boreness (or a secondary y-axis) to make threshold crossings visible.

## Step H2 (a.k.a. H′) — Intrinsic-frequency heterogeneity + merge instrumentation (seed = 0)

### Goal
Avoid the trivial absorbing regime observed in the homogeneous-oscillator setup (full phase lock + single stable mega-cluster), by introducing **agent-specific intrinsic frequencies** and by instrumenting **join/detach/merge** events to relate assembly dynamics to phase coherence.

### Code changes (conceptual)
1) **Heterogeneous oscillators**:
   - Sample per-agent intrinsic frequencies at init:
     - ω₀,k ~ Normal(ω₀, ω₀,σ), k = 1..N
   - Phase update uses ω₀,k (and optional phase noise), wrapped mod 1.

2) **Event instrumentation**:
   - Log per-step counts:
     - n_joined, n_detached, n_merges
   - Produce plots with “merge markers” (vertical lines) to visually correlate merge events with:
     - assembly indicators (n_clusters, mean_cluster_size)
     - global phase coherence R(t)

### Run command
python -m ecfi.run --config configs/base.yaml --seed 0

### Config snapshot (key params)
- sim: dt = 0.05, steps = 3000
- agents: N = 50, vmax = 1.2, noise_sigma = 0.10
- neighbors: Rp = 1.4
- assembly: Rc = 0.65, max_degree = 4, Tmin = 20, detach_base_p = 0.008
- osc: omega0 = 0.15, omega0_sigma = 0.01, phase_noise_sigma = 0.00, sync_mode = anchor
- cognition: tau_c = 1.0, g = 0.6, alpha = 0.9, beta_I = 0.8, beta_C = -0.5, beta_N = 0.0
- objective: init_weights = [0.60, 0.15, 0.25], update_rate = 0.25, relax_rate = 0.005
- constraints: features_ema = 0.12, lambda = 0.20, eta = 0.05, b_max = 0.03, c_max = 4.3,
  event_ema = 0.25, gamma = [0.40, 0.55, 0.25, 0.60]
- policy: k_align = 0.55, k_cohesion = 0.45, k_sep = 1.40, R_sep = 0.40, damp = 0.06

### Outputs (artifacts)
- outputs/run/global.csv
- outputs/run/agents.csv
- outputs/run/config_resolved.json
- Figures (seed 0):
  - docs/figures/H2_seed0/H2_plot_clusters_seed0.png
  - docs/figures/H2_seed0/H2_plot_coherence_seed0.png
  - docs/figures/H2_seed0/H2_plot_events_assembly_seed0.png
  - docs/figures/H2_seed0/H2_plot_events_coherence_seed0.png
  - docs/figures/H2_seed0/H2_plot_events_counts_seed0.png
  - docs/figures/H2_seed0/H2_plot_intrinsic_seed0.png
  - docs/figures/H2_seed0/H2_plot_events_intrinsic_seed0.png

### Empirical summary (from global.csv; post burn-in t > 200)
- Coherence R(t):
  - mean ≈ 0.939, std ≈ 0.036, min ≈ 0.782, max ≈ 0.998
  - first time R(t) ≥ 0.95 occurs around t ≈ 210
- Assembly regime:
  - n_clusters: mean ≈ 14.4 (range ≈ 3..25), std ≈ 5.82
  - mean_cluster_size: mean ≈ 3.70 (range ≈ 2.00..16.67), std ≈ 1.56
- Intrinsic signals (global means):
  - mean_novelty ≈ 0.312
  - mean_boreness ≈ 0.012 (stays near zero)
  - mean_load ≈ 1.91 (moderate, slowly varying)
- Event statistics (per step; post burn-in):
  - E[n_joined] ≈ 0.094
  - E[n_detached] ≈ 0.116
  - E[n_merges] ≈ 0.179
  - merges occur in ~16% of steps (n_merges > 0)

### Qualitative read of the figures
1) **No more absorbing mega-cluster**: with ω₀ heterogeneity, the system does not collapse into a single stable component. Instead, it exhibits persistent fragmentation and re-aggregation: n_clusters fluctuates widely, and mean cluster size remains moderate.
2) **High but non-perfect coherence**: global coherence rapidly increases toward ~1, but then remains in a “near-synchronized” regime with dips and recoveries. This is consistent with: (i) periodic anchoring on merges + (ii) subsequent phase drift caused by ω₀,k mismatch.
3) **Merge events as regime perturbations**: merge markers are dense. Coherence tends to be slightly lower on merge steps, suggesting that merge activity is one driver of coherence perturbations (or vice-versa), rather than a passive by-product.
4) **Boreness stays almost zero**: in this run, novelty spikes are frequent enough that boreness never accumulates meaningfully; load remains moderate and structured.

### Interpretation (working hypothesis)
Adding ω₀ heterogeneity moves the system from an “absorbing lock-in” to a **metastable regime**:
- anchoring on merges produces episodic phase alignment,
- heterogeneous ω₀,k reintroduces drift,
- drift sustains ongoing join/detach/merge activity,
- the result is persistent reconfiguration under high but imperfect global coherence.

### Next step (H3 / H″): make synchronization *soft* and state-dependent
Current sync_mode = anchor is still a hard reset. Two natural upgrades:

A) **Soft anchoring on merges**
- On merge events, instead of setting all phases equal to anchor_phase, apply partial relaxation:
  phase_n ← (1−ρ)·phase_n + ρ·anchor_phase  (mod 1), with ρ ∈ (0,1)
- Optionally make ρ depend on (cluster_size, novelty, or weights).

B) **Kuramoto-style coupling (edge- or neighbor-based)**
- dθ_k/dt = ω₀,k + K * (1/deg_k) Σ_{j∈neigh(k)} sin(2π(θ_j−θ_k))
- Let K be modulated by cognition/objective weights, e.g. K = K0 * wC or K = K0 * (1 − novelty).

Deliverables planned for H3:
- add (ρ or K) parameters to config
- rerun seed sweep (0..9) to check robustness
- extend trace with a small table summarizing mean coherence, mean n_clusters, merge frequency across seeds