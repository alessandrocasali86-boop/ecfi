# Changelog
All notable changes to this project will be documented in this file.

The format is based on "Keep a Changelog", and this project uses Semantic Versioning.

## [Unreleased]
### Added
### Changed
### Fixed

## [0.2.0] - 2026-08-21
First public release.

### Added
- MIT licence (`LICENSE`).
- Complete README covering the project, install, both simulation configs, the
  output schema, the sonification CLI, the audio synthesis step, the Audio-TDA
  pipeline, reproducibility, the data deposit, licensing and citation.
- Smoke test (`tests/test_smoke.py`): runs a short simulation and asserts that the
  expected output files, row counts and columns are produced.
- MP3 renderings of the three sonifications, tracked under `audio/`, so the
  repository is audible without downloading the lossless deposit.
- `docs/TRACE.md` entry for the 2026-08-19 release audit: recovery of the audio
  artifacts, identification of the `base` variant and of the synthesis engine, and
  a cross-platform verification of the Audio-TDA results.

### Changed
- `.gitignore` consolidated into a single set of rules. The previous file
  contained two overlapping blocks in which a bare `outputs/` rule silently
  cancelled the `!outputs/.gitkeep` exception; lossless `*.wav` files remain
  excluded, `audio/` and `*.mp3` no longer are.
- `CITATION.cff` updated to 0.2.0.

### Fixed
- Missing changelog entries for 0.1.5 and 0.1.6, reconstructed from the tagged
  history: `CITATION.cff` declared v0.1.5 and the repository carried a v0.1.6 tag
  while this file stopped at 0.1.4.

## [0.1.6] - 2026-03-06
### Added
- `CITATION.cff` with citation metadata for the repository.

## [0.1.5] - 2026-03-06
### Added
- Audio-TDA pipeline (`scripts/tda_audio_vr.py`): Vietoris–Rips persistence on
  PCA-reduced log-mel frames, persistence diagrams, and pairwise Wasserstein
  distances across the base/thin/faithful sonifications.
- Curated results under `audio_tda_out_nowarn/`: distances CSV, diagrams, analysis
  parameters (`config.json`) and the recorded environment (`run_config.json`).
- Pinned dependency set (`requirements.txt`, `requirements.lock`) and development
  tooling (`requirements-dev.txt`).

### Changed
- README: clearer setup, simulation and Audio-TDA instructions.
- `.gitignore`: keep the curated `audio_tda_out_nowarn/` artifacts while ignoring
  the other TDA output directories.

## [0.1.4] - 2026-03-03
### Added
- Faithful Lucas-like division rule: new --division_mode faithful generates c:b intra-cycle subdivisions (multi-events per cycle) from phase wraps.
- A/B comparison supported via --out_mid / --out_xml for thin vs faithful renders.

### Changed
- Sonification CLI extended: --division_mode {thin,faithful}.

## [0.1.3] - 2026-03-03
### Added
- Sonification MVP: music21-based renderer to export MIDI and MusicXML from agents.csv phase-wrap events (ecfi/sonify/render_m21.py).
- Minimal requirements.txt (numpy, pyyaml, music21).


## [0.1.2] - 2026-03-03
### Added
- H1 (regime-switch) baseline artifacts: resolved config, global log, and core diagnostic plots (seed=0) under docs/runs/ and docs/figures/.

### Changed
- (none)

### Fixed
- (none)

## [0.1.1] - 2026-03-03
### Added
- First runnable E-CFI prototype (sim+assembly+cognition+signals) with base config.
- Baseline mini-paper report (docs/ecfi_minipaper_trace.tex) and core diagnostic figures (clusters/coherence/intrinsic).

## [0.1.0] - 2026-03-02
### Added
- Baseline repository structure (configs/, docs/, ecfi/, tests/, outputs/.gitkeep).
