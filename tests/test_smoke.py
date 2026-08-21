"""Smoke test: a short simulation must produce well-formed outputs.

`ecfi.run` exposes only ``--config`` and ``--seed`` and reads the output
directory from the config itself, so this test writes a reduced copy of
``configs/base.yaml`` into ``tmp_path`` rather than passing CLI overrides.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STEPS = 20

# Columns that ecfi/sonify/render_m21.py requires from agents.csv. Asserting
# them here means the smoke test also protects the sonification input contract.
SONIFY_COLUMNS = {"t", "id", "phase", "degree", "cluster_id", "cluster_size", "load"}


def _run_short_simulation(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load((REPO_ROOT / "configs" / "base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["steps"] = STEPS
    cfg["logging"]["out_dir"] = str(tmp_path / "run")

    cfg_path = tmp_path / "smoke.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    subprocess.run(
        [sys.executable, "-m", "ecfi.run", "--config", str(cfg_path), "--seed", "0"],
        cwd=REPO_ROOT,
        check=True,
    )
    return tmp_path / "run"


def test_short_run_produces_expected_outputs(tmp_path):
    cfg = yaml.safe_load((REPO_ROOT / "configs" / "base.yaml").read_text(encoding="utf-8"))
    n_agents = cfg["agents"]["N"]

    out_dir = _run_short_simulation(tmp_path)

    agents_csv = out_dir / "agents.csv"
    global_csv = out_dir / "global.csv"
    resolved = out_dir / "config_resolved.json"

    for path in (agents_csv, global_csv, resolved):
        assert path.exists(), f"{path.name} was not written"

    with agents_csv.open(newline="", encoding="utf-8") as fh:
        agent_rows = list(csv.DictReader(fh))

    # the runner logs steps 1..steps, one row per agent per logged step
    assert len(agent_rows) == STEPS * n_agents
    assert SONIFY_COLUMNS <= set(agent_rows[0])
    assert {int(row["t"]) for row in agent_rows} == set(range(1, STEPS + 1))
    assert {int(row["id"]) for row in agent_rows} == set(range(n_agents))

    # phase is the quantity the sonification keys on: it must stay in [0, 1)
    phases = [float(row["phase"]) for row in agent_rows]
    assert all(0.0 <= p < 1.0 for p in phases)

    with global_csv.open(newline="", encoding="utf-8") as fh:
        global_rows = list(csv.DictReader(fh))

    assert len(global_rows) == STEPS
    assert {"coherence", "n_clusters", "mean_cluster_size"} <= set(global_rows[0])
    assert all(0.0 <= float(row["coherence"]) <= 1.0 for row in global_rows)

    assert json.loads(resolved.read_text(encoding="utf-8"))["sim"]["steps"] == STEPS


def test_run_is_deterministic_on_this_platform(tmp_path):
    """Same seed, same machine, same bytes.

    Cross-platform reproduction is a different matter — see README §8.
    """
    first = (_run_short_simulation(tmp_path / "a") / "global.csv").read_bytes()
    second = (_run_short_simulation(tmp_path / "b") / "global.csv").read_bytes()
    assert first == second
