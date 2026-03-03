from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from ecfi.sim.world import World


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="E-CFI demo simulation runner")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config")
    parser.add_argument("--seed", type=int, default=None, help="Override config seed")
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    cfg = load_yaml(cfg_path)

    if args.seed is not None:
        cfg["seed"] = int(args.seed)

    out_dir = Path(cfg["logging"]["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save resolved config for reproducibility
    with (out_dir / "config_resolved.json").open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    world = World(cfg)
    world.run()

    print(f"Done. Outputs in: {out_dir.resolve()}")


if __name__ == "__main__":
    main()