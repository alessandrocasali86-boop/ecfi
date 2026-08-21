# ecfi — Embodied Collective Free Improvisation

A minimal demo simulation of Embodied Collective Free Improvisation (E-CFI) plus a
small Audio-TDA pipeline.

Agents are embodied phase oscillators moving on a torus. They form and dissolve
*assemblies* (short-lived coupled ensembles) according to proximity and degree
constraints, and each agent carries an internal objective — a weighted mixture of
*intention*, *cohesion* and *novelty* — that is revised endogenously whenever
boreness (the CFI literature's term for accumulated boredom) or perceptual load
cross their thresholds. The resulting phase-wrap events
are sonified into a score (MIDI + MusicXML) through a Lucas-like `c:b` division
rule, and the rendered audio is analysed with persistent homology: Vietoris–Rips
complexes on PCA-reduced log-mel frames, compared pairwise by Wasserstein distance.

This repository is the companion artifact of a paper accepted at CIM 2026
(*Embodied Collective Free Improvisation*). It contains the simulator, the
sonification renderer, the Audio-TDA script, and the curated results cited in the
paper.

---

## 1. Repository layout

```
ecfi/                    simulation package
  run.py                 CLI entry point
  sim/                   world, neighbourhoods, torus geometry
  assembly/              assembly formation and dissolution rules
  cognition/             intention dynamics and objective revision
  signals/               novelty, boreness, perceptual load
  sonify/render_m21.py   score renderer (music21)
  viz/                   diagnostic plots
configs/                 base.yaml, regime_switch.yaml
scripts/tda_audio_vr.py  Audio-TDA pipeline
audio_tda_out_nowarn/    curated TDA results cited in the paper
docs/TRACE.md            chronological lab notebook
docs/runs/               frozen run metadata (H1, seed 0)
docs/figures/            frozen diagnostic figures
outputs/                 run outputs (git-ignored)
```

---

## 2. Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Three requirement files are provided:

| File | Purpose |
|---|---|
| `requirements.txt` | loose dependency list — use this for a normal install |
| `requirements.lock` | fully pinned environment; use it to reproduce the published results exactly |
| `requirements-dev.txt` | development tooling (pytest, ruff, black, mypy, jupyter) |

The published results were produced with Python 3.9.6 (macOS, clang 17), numpy
2.0.2 and librosa 0.11.0; the full environment is recorded in
`audio_tda_out_nowarn/run_config.json`.

---

## 3. Run a simulation

```bash
python -m ecfi.run --config configs/base.yaml --seed 0
python -m ecfi.viz.plot_run --run_dir outputs/run
```

`--seed` overrides the seed declared in the config. The resolved configuration is
always written to `outputs/run/config_resolved.json`, so any run can be replayed
from its own output directory.

`python -m ecfi.viz.plot_events --run_dir outputs/run` produces the phase-event
view in addition to the three standard diagnostics.

### The two configurations

Both run 50 agents for 3000 steps at `dt = 0.05` on a 10×10 torus, and differ in
how strongly the collective is held together:

| | `base.yaml` | `regime_switch.yaml` |
|---|---|---|
| perception radius `Rp` | 1.6 | 1.4 |
| assembly radius `Rc` | 0.7 | 0.65 |
| min. assembly lifetime `Tmin` | 40 | 20 |
| spontaneous detachment `detach_base_p` | 0.001 | 0.008 |
| boreness threshold `b_max` | 1.0 | 0.03 |
| load threshold `c_max` | 6.0 | 4.3 |
| objective update rate | 0.15 | 0.25 |
| initial weights (wI, wC, wN) | 0.70 / 0.20 / 0.10 | 0.60 / 0.15 / 0.25 |
| cohesion gain `k_cohesion` | 0.7 | 0.45 |
| oscillator spread `omega0_sigma` | — | 0.01 |
| coupling `sync_strength` | — | 0.35 |

- **`base.yaml`** is the lock-in baseline: the population collapses rapidly into a
  single assembly and stays in near-permanent phase lock (final coherence 1.0,
  one cluster of 50 agents).
- **`regime_switch.yaml`** is the tuned regime-switching run. Boreness and load
  thresholds are low enough to fire routinely, objectives are revised faster and
  cohesion is weaker, so several coalitions coexist, merge and break apart without
  the system ever locking (final coherence ≈ 0.90, ~22 clusters).

Frozen artifacts for the regime-switch run at seed 0 are in
`docs/runs/h1_regime_switch_seed0_*` and `docs/figures/h1_regime_switch_seed0/`.

---

## 4. Output format

A run writes three files to `logging.out_dir` (default `outputs/run`):
`config_resolved.json`, `agents.csv` (one row per agent per step — 150 001 rows
for the default 50 agents × 3000 steps) and `global.csv` (one row per step).

**`agents.csv`**

| Column | Meaning |
|---|---|
| `t` | step index (multiply by `sim.dt` for seconds) |
| `id` | agent index, 0…N−1 |
| `x`, `y` | position on the torus |
| `vx`, `vy` | velocity |
| `phase` | oscillator phase in [0, 1); a *wrap* is a step where `phase` decreases |
| `omega0` | intrinsic oscillator frequency |
| `degree` | number of current assembly links |
| `cluster_id` | connected component of the assembly graph |
| `cluster_size` | size of that component |
| `local_coh` | local Kuramoto order parameter over self + neighbours |
| `novelty` | ‖ΔF‖, the change in the agent's 3-D feature vector |
| `boreness` | leaky accumulator of low novelty |
| `load` | perceptual load, γ·(neighbours, degree, event rate, novelty) |
| `wI`, `wC`, `wN` | current objective weights (intention, cohesion, novelty) |
| `omega_norm` | norm of the agent's intention vector |

**`global.csv`**

| Column | Meaning |
|---|---|
| `t` | step index |
| `mean_speed` | mean agent speed |
| `coherence` | global Kuramoto order parameter |
| `n_clusters` | number of assembly components |
| `mean_cluster_size` | mean component size |
| `n_edges` | number of assembly links |
| `mean_novelty`, `mean_boreness`, `mean_load` | population means |
| `n_joined`, `n_detached`, `n_merges` | assembly events this step |
| `mean_omega0`, `std_omega0` | intrinsic frequency statistics |

---

## 5. Sonification

```bash
python -m ecfi.sonify.render_m21 --run_dir outputs/run --dt 0.05 \
  --division_mode thin --out_mid outputs/run/sonification_thin.mid \
  --out_xml outputs/run/sonification_thin.musicxml
```

The renderer reads phase-wrap events from `agents.csv`, maps them onto a major
pentatonic scale, quantises them to a rhythmic grid and writes MIDI and MusicXML.

> **Note on `--dt`.** The renderer's default is `0.02`, while both shipped configs
> run at `dt = 0.05`. Pass `--dt 0.05` explicitly (or the value from
> `config_resolved.json`) so that event times are mapped to the correct wall-clock
> seconds.

### Division modes

Each agent is assigned a `c:b` rule deterministically from `--division_set`, seeded
by `--division_seed`.

- **`thin`** — approximation. Keeps one event every *m* ≈ round(c/b) phase wraps.
  Because it only ever thins wraps, it cannot produce more than one event per
  cycle.
- **`faithful`** — true intra-cycle subdivision. Takes non-overlapping blocks of
  *c* consecutive cycles and generates *b* evenly spaced events inside each block,
  then samples agent state at the nearest timestep for each scheduled event.

### Parameters

| Flag | Default | Meaning |
|---|---|---|
| `--run_dir` | `outputs/run` | directory containing `agents.csv` |
| `--out_mid` / `--out_xml` | `outputs/run/sonification.{mid,musicxml}` | output paths |
| `--dt` | `0.02` | simulation timestep in seconds — **set to match your config** |
| `--bpm` | `120.0` | tempo used for quantisation and for the score |
| `--grid_div` | `4` | grid subdivisions per quarter (4 → sixteenths) |
| `--parts` | `4` | number of parts; agent *k* is written to part *k* mod `parts` |
| `--root` | `60` | root MIDI note of the pentatonic scale (60 = C4) |
| `--max_events` | `1200` | cap on total events, to keep the score readable |
| `--time_signature` | `4/4` | time signature |
| `--division_mode` | `thin` | `thin` or `faithful` |
| `--division_set` | `1:1,2:1,3:1,4:1` | comma-separated `c:b` rules |
| `--division_seed` | `0` | seed for the per-agent rule assignment |
| `--cluster_transpose` | `fifths` | `none`, or a circle-of-fifths transposition by `cluster_id` |

Note duration is derived from `cluster_size` and velocity from `load`, so both the
assembly structure and the perceptual state of each agent are audible.

---

## 6. Audio synthesis

The three WAV files analysed in the paper were rendered from the sonification
scores with **MuseScore Studio 4.6.4** (revision `8af129b`), using its built-in
sounds — the scores carry four generic parts with no explicit instrument
assignment, and no custom soundfont was installed. MuseScore's audio export
produced 32-bit float stereo WAV at 44.1 kHz, together with the MP3 versions kept
alongside them.

The intermediate MuseScore scores are preserved as `.mscz` files next to the MIDI
exports.

> **Honest caveat.** This synthesis step was reconstructed after the fact from the
> file metadata; it was never scripted, and the exact export session cannot be
> replayed. In particular the MIDI and MusicXML files currently in `outputs/run/`
> do **not** correspond note-for-note to the rendered audio: they were regenerated
> later with the current `--max_events` cap and are shorter than the audio. The
> WAV files are therefore treated as **primary data**, not as a derived artifact —
> they are deposited as such (see §7) and the published TDA results are computed
> from them directly.
>
> Anyone wishing to synthesise fresh audio from a new run can open the exported
> MusicXML in MuseScore 4 and use *File → Export → WAV*; the result will be a
> different realisation, statistically comparable but not identical.

### The three variants

| File | Duration | Description |
|---|---|---|
| `sonification_base.wav` | 3′04.8″ | **reference rendering**, predating the `thin`/`faithful` A/B comparison — the original MVP sonification of the `base.yaml` run, before the `c:b` division machinery was introduced |
| `sonification_thin.wav` | 3′04.8″ | `--division_mode thin` |
| `sonification_faithful.wav` | 3′11.5″ | `--division_mode faithful` |

All three are 44.1 kHz stereo 32-bit float. `base` is **not** a division mode: it
is the baseline against which the two division rules are compared. Its waveform
correlates at 0.91 with the earlier `ecfi_sonification_sample_4agents.wav` export
and at only 0.26 with `sonification_thin.wav`, confirming that the three files are
genuinely distinct realisations rather than re-exports of one another.

---

## 7. Audio-TDA pipeline

```bash
python scripts/tda_audio_vr.py \
  --audio_dir audio \
  --out_dir audio_tda_out_nowarn \
  --n_mels 40 \
  --max_frames 400 \
  --pca_dim 8 \
  --maxdim 2 \
  --wasserstein_p 1 \
  --frame_sampling uniform \
  --plot_mode both
```

Each file is loaded mono at 22 050 Hz (librosa resamples from the 44.1 kHz
originals), converted to a log-mel spectrogram, reduced to 8 PCA dimensions and
sampled down to 400 uniformly spaced frames. Vietoris–Rips persistence is computed
up to H2 and diagrams are compared pairwise by Wasserstein distance with *p* = 1.

`audio_tda_out_nowarn/` holds the curated results cited in the paper:
`wasserstein_distances.csv`, the persistence diagrams, the analysis parameters in
`config.json`, and the exact environment in `run_config.json`.

Published distances (*p* = 1):

| | H0 | H1 | H2 |
|---|---|---|---|
| base vs faithful | 44.9510 | 20.0288 | 7.7648 |
| base vs thin | 23.1642 | 20.5156 | 7.4133 |
| faithful vs thin | 26.3014 | 22.4645 | 7.7427 |

The MP3 renderings are tracked in `audio/` so the sonifications can be listened to
straight from a clone. The lossless WAV masters are ~200 MB in total and stay out
of git; they are deposited separately (see §9). Put them in `audio/` before running
the pipeline — the script prefers `.wav` over `.mp3` when both are present, and the
published distances were computed from the lossless files.

---

## 8. Reproducibility

**The Audio-TDA results reproduce exactly.** Re-running the command above on the
deposited WAV files under Python 3.11 / numpy 2.4.4 / librosa 0.11.0 on Linux —
against Python 3.9.6 / numpy 2.0.2 / librosa 0.11.0 on macOS for the published
run — reproduces all nine distances to within 1.13 × 10⁻⁴ absolute (≈ 2 × 10⁻⁶
relative), i.e. identically at the four decimal places reported in the paper. The
persistent-homology results are therefore platform-independent, provided the same
audio files are used as input.

**Single simulator trajectories are not bit-reproducible across platforms.** The
simulator is deterministic for a fixed seed on a fixed platform, but the dynamics
are nonlinear and amplify floating-point differences. Regenerating the
regime-switch run at seed 0 on a different machine and comparing against the frozen
artifact in `docs/runs/` shows divergence beginning at row 2, in the 16th decimal
place, and growing: final coherence 0.903 (frozen) against 0.769 (regenerated), and
mean `n_clusters` 14.56 against 18.25 over the run. This is why the paper reports
seed-averaged statistics rather than individual trajectories.

The practical consequence is that audio regenerated on a different machine would be
a *different realisation* — statistically comparable, not identical — and the
distances in §7 would not reproduce exactly from a fresh simulation. Recovering and
depositing the original WAV files, rather than regenerating them, is what makes the
published numbers verifiable.

---

## 9. Data deposit

The three lossless WAV files are too large for version control. They are
deposited on Zenodo as a separate dataset:
[doi:10.5281/zenodo.22041198](https://doi.org/10.5281/zenodo.22041198).
Each is 44.1 kHz stereo 32-bit float, rendered as described in §6 — note that the
Audio-TDA pipeline resamples them to 22 050 Hz on load. Download them into
`audio/` to re-run the pipeline.

The MP3 renderings of the same three files are tracked in `audio/`.

---

## 10. Licence

Released under the **MIT Licence** — see [`LICENSE`](LICENSE).

The companion repository `nidi_grammar` is released under CC-BY 4.0, which suits a
repository containing analytical material and notation as well as code. `ecfi` is
pure software, and Creative Commons licences are explicitly not recommended for
software: they say nothing about patent grants, warranty disclaimers or source
availability. The difference between the two repositories is deliberate.

---

## 11. Citation

Citation metadata is in [`CITATION.cff`](CITATION.cff); GitHub renders it as a
ready-made BibTeX entry via *Cite this repository*.

Please cite the archived Zenodo DOIs rather than the bare GitHub URL — DOIs are
permanent and versioned:

- **Code** (this repository, v0.2.0):
  [doi:10.5281/zenodo.22041071](https://doi.org/10.5281/zenodo.22041071) —
  concept DOI for all versions:
  [doi:10.5281/zenodo.22041070](https://doi.org/10.5281/zenodo.22041070)
- **Audio dataset** (lossless WAV):
  [doi:10.5281/zenodo.22041198](https://doi.org/10.5281/zenodo.22041198)

The paper describing the model will be added here once published:

> A. Casali, *Embodied Collective Free Improvisation (E-CFI): Posthuman Swarm
> Coordination for Emergent Musical Form*, Proceedings of the XXV Colloquio di
> Informatica Musicale (CIM 2026), L'Aquila, 2026. *(forthcoming)*
