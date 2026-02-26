from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np


@dataclass
class Agent:
    idx: int
    pos: np.ndarray  # shape (2,)
    vel: np.ndarray  # shape (2,)


class World:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.dt = float(cfg["sim"]["dt"])
        self.steps = int(cfg["sim"]["steps"])

        self.domain = cfg["env"]["domain"]
        self.size = np.array(cfg["env"]["size"], dtype=float)

        self.N = int(cfg["agents"]["N"])
        self.vmax = float(cfg["agents"]["vmax"])
        self.noise_sigma = float(cfg["agents"]["noise_sigma"])

        self.seed = int(cfg.get("seed", 0))
        self.rng = np.random.default_rng(self.seed)

        self.out_dir = Path(cfg["logging"]["out_dir"])
        self.log_every = int(cfg["logging"]["every"])

        self.t = 0

        self.agents: List[Agent] = self._init_agents()

        # prepare logs
        self._agents_csv = self.out_dir / "agents.csv"
        self._global_csv = self.out_dir / "global.csv"
        self._init_logs()

    def _init_agents(self) -> List[Agent]:
        agents: List[Agent] = []
        for k in range(self.N):
            pos = self.rng.random(2) * self.size  # uniform in box
            theta = self.rng.random() * 2 * np.pi
            vel = np.array([np.cos(theta), np.sin(theta)], dtype=float) * (0.2 * self.vmax)
            agents.append(Agent(idx=k, pos=pos, vel=vel))
        return agents

    def _wrap_torus(self, pos: np.ndarray) -> np.ndarray:
        # torus wrap-around
        return np.mod(pos, self.size)

    def step(self) -> None:
        # Simple motion: velocity + noise, bounded, torus wrap.
        for a in self.agents:
            noise = self.rng.normal(0.0, self.noise_sigma, size=2)
            a.vel = a.vel + noise * np.sqrt(self.dt)

            speed = float(np.linalg.norm(a.vel))
            if speed > self.vmax:
                a.vel = a.vel / speed * self.vmax

            a.pos = a.pos + a.vel * self.dt

            if self.domain == "torus":
                a.pos = self._wrap_torus(a.pos)
            else:
                # fallback: clip into box
                a.pos = np.clip(a.pos, [0.0, 0.0], self.size)

        self.t += 1

    def run(self) -> None:
        for _ in range(self.steps):
            self.step()
            if self.t % self.log_every == 0:
                self._log()

        self._close_logs()

    def _init_logs(self) -> None:
        self._agents_f = self._agents_csv.open("w", newline="", encoding="utf-8")
        self._global_f = self._global_csv.open("w", newline="", encoding="utf-8")

        self._agents_writer = csv.writer(self._agents_f)
        self._global_writer = csv.writer(self._global_f)

        self._agents_writer.writerow(["t", "id", "x", "y", "vx", "vy"])
        self._global_writer.writerow(["t", "mean_speed"])

    def _log(self) -> None:
        speeds: List[float] = []
        for a in self.agents:
            speeds.append(float(np.linalg.norm(a.vel)))
            self._agents_writer.writerow([self.t, a.idx, a.pos[0], a.pos[1], a.vel[0], a.vel[1]])

        self._global_writer.writerow([self.t, float(np.mean(speeds))])

    def _close_logs(self) -> None:
        self._agents_f.close()
        self._global_f.close()