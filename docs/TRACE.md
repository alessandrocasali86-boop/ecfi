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

---

## 2026-03-06
### Audio TDA (VR on log-mel frames) — run stable (no RuntimeWarning)

Command:
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

Results (Wasserstein, p=1):
H0:
  base vs faithful = 44.9510
  base vs thin     = 23.1642
  faithful vs thin = 26.3014
H1:
  base vs faithful = 20.0288
  base vs thin     = 20.5156
  faithful vs thin = 22.4645
H2:
  base vs faithful =  7.7648
  base vs thin     =  7.4133
  faithful vs thin =  7.7427

Outputs:
- audio_tda_out_nowarn/*_vr_diagrams.png
- audio_tda_out_nowarn/wasserstein_distances.csv

Released as v0.1.5.

---

## 2026-08-19
### Release audit — artifact recovery, provenance, cross-platform verification

- Context: preparing the repository for public release as the companion artifact
  of the CIM 2026 paper. Four questions were open: where the git-ignored audio
  and run outputs were, what the `base` sonification variant actually is, which
  tool synthesised the WAV files, and whether the published TDA results survive a
  change of platform.

#### 1. Artifact recovery

Both the audio and the original run outputs were still present in the local
working copy.

- `audio/`: `sonification_base.wav` (184.75 s), `sonification_thin.wav`
  (184.75 s), `sonification_faithful.wav` (191.50 s), all 44.1 kHz stereo
  32-bit float; plus MP3 renderings of each (~2.6 MB apiece).
- `outputs/run/`: `agents.csv` (150 001 rows), `global.csv` (3 001),
  `config_resolved.json` (the `base.yaml` configuration, not
  `regime_switch.yaml`), the three diagnostic plots, MIDI and MusicXML for the
  default/`thin`/`faithful` renders, two MuseScore `.mscz` files, and an earlier
  export `ecfi_sonification_sample_4agents.wav`.

Caveat recorded: `agents.csv` is dated 2026-03-06 while the MIDI exports are
dated 2026-03-03, so the CSV was regenerated after the scores were rendered.

#### 2. What `base` is

`base` is **not** a division mode. It is the MVP sonification of the `base.yaml`
run, produced before the `c:b` division mechanism existed, and serves as the
reference against which `thin` and `faithful` are compared.

Evidence:
- waveform correlation `base` vs `thin` = 0.26, i.e. genuinely distinct audio;
- waveform correlation `base` vs `ecfi_sonification_sample_4agents.wav` = 0.91 at
  zero lag, with identical frame counts;
- `sonification.mid` is byte-identical to `sonification_faithful.mid`, so the
  unnamed default export is a `faithful` render and cannot be `base`;
- `render_m21.py` defaults to `--division_mode thin`, ruling out the earlier
  guess that `base` was "the default with `division_set` 1:1".

#### 3. Synthesis engine

**MuseScore Studio 4.6.4**, revision `8af129b`, read from the `.mscz` files in
`outputs/run/`. Internal sounds, no soundfont installed, four generic parts with
no instrument assignment. Export format: 32-bit float 44.1 kHz stereo WAV with
MP3 versions alongside.

Limitation recorded: the MIDI and MusicXML currently in `outputs/run/` do not
correspond to the rendered audio — the scores are 16 and 44 measures (32 s and
88 s at 120 bpm) against 185 s and 191.5 s of audio, and the `faithful` score is
the shorter one while its audio is the longer, which no uniform tempo can
reconcile. They were regenerated later under the current `--max_events` cap. The
exact synthesis session is not recoverable, so the WAV files are treated as
primary data rather than as a derived artifact.

#### 4. Cross-platform verification of the Audio-TDA results

- Command: as in the 2026-03-06 entry above, unchanged.
- Environment: Linux, Python 3.11.15, numpy 2.4.4, librosa 0.11.0, scipy 1.17.1.
- Reference: the published run on macOS, Python 3.9.6, numpy 2.0.2,
  librosa 0.11.0 (recorded in `audio_tda_out_nowarn/run_config.json`).
- Result: all nine Wasserstein distances reproduced, maximum absolute deviation
  **1.13 × 10⁻⁴** (≈ 2 × 10⁻⁶ relative) — identical at the four decimal places
  reported in the paper.

Conclusion: the persistent-homology results are platform-independent given the
same audio input. This is disjoint from the simulator's floating-point
sensitivity, which affects single trajectories but not this pipeline. Depositing
the original WAV files, rather than regenerating them, is what makes the
published distances verifiable.

Technical note: on Python ≥ 3.11 `ripser`/`persim` fail to install because
`hopcroftkarp` no longer builds. Workaround: install `persim==0.3.7` and `ripser`
with `--no-deps`, then copy the `hopcroftkarp` package manually from its sdist.
`persim.wasserstein` does not use it.

- Files changed: `LICENSE` (new), `README.md`, `CHANGELOG.md`, `CITATION.cff`,
  `.gitignore`, `tests/test_smoke.py` (new), this file.
- Next: tag v0.2.0, GitHub release, Zenodo deposits (code via the GitHub
  integration, lossless audio as a separate dataset upload).

---

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
