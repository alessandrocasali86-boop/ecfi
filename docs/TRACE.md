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
