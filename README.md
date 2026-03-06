# ecfi

Embodied Collective Free Improvisation (E-CFI) demo simulation.

## Quick start (planned)
- `python -m ecfi.run --config configs/base.yaml --seed 0`

## Repo layout
- `ecfi/` Python package
- `configs/` YAML configs
- `outputs/` generated runs (not versioned, except `.gitkeep`)
- `docs/` notes (e.g., architecture)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt