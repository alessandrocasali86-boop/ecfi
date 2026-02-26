from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ecfi.sim.neighbors import compute_neighbors_torus
from ecfi.assembly.rules import apply_join_detach, Edge
from ecfi.assembly.components import UnionFind


@dataclass
class Agent:
    idx: int
    pos: np.ndarray  # shape (2,)
    vel: np.ndarray  # shape (2,)
    phase: float     # in [0,1)


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

        # neighbors + assembly
        self.Rp = float(cfg["neighbors"]["Rp"])
        self.Rc = float(cfg["assembly"]["Rc"])
        self.max_degree = int(cfg["assembly"]["max_degree"])
        self.Tmin = int(cfg["assembly"]["Tmin"])
        self.detach_base_p = float(cfg["assembly"]["detach_base_p"])

        # oscillators
        self.omega0 = float(cfg["osc"]["omega0"])
        self.phase_noise_sigma = float(cfg["osc"].get("phase_noise_sigma", 0.0))
        self.sync_mode = str(cfg["osc"].get("sync_mode", "anchor"))

        # logging
        self.out_dir = Path(cfg["logging"]["out_dir"])
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_every = int(cfg["logging"]["every"])

        self.t = 0

        self.agents: List[Agent] = self._init_agents()

        # assembly state
        self.edges: dict[tuple[int, int], Edge] = {}
        self.degrees = np.zeros(self.N, dtype=int)
        self.cluster_id = np.full(self.N, -1, dtype=int)

        # placeholder constraints (next step)
        self.boreness = np.zeros(self.N, dtype=float)

        # prepare logs
        self._agents_csv = self.out_dir / "agents.csv"
        self._global_csv = self.out_dir / "global.csv"
        self._init_logs()

    def _init_agents(self) -> List[Agent]:
        agents: List[Agent] = []
        for k in range(self.N):
            pos = self.rng.random(2) * self.size
            theta = self.rng.random() * 2 * np.pi
            vel = np.array([np.cos(theta), np.sin(theta)], dtype=float) * (0.2 * self.vmax)
            phase = float(self.rng.random())
            agents.append(Agent(idx=k, pos=pos, vel=vel, phase=phase))
        return agents

    def _wrap_torus(self, pos: np.ndarray) -> np.ndarray:
        return np.mod(pos, self.size)

    def _coherence(self) -> float:
        phases = np.array([a.phase for a in self.agents], dtype=float)
        z = np.exp(2j * np.pi * phases)
        return float(np.abs(np.mean(z)))

    def step(self) -> None:
        # --- 1) oscillator update (free-running) + firing events (kept for later)
        fired = np.zeros(self.N, dtype=int)
        for a in self.agents:
            noise = self.rng.normal(0.0, self.phase_noise_sigma) * np.sqrt(self.dt)
            a.phase += self.omega0 * self.dt + noise
            if a.phase >= 1.0:
                a.phase -= 1.0
                fired[a.idx] = 1
            elif a.phase < 0.0:
                a.phase += 1.0

        # --- 2) pre-join components (to detect merges)
        uf_old = UnionFind(self.N)
        for (i, j), _e in self.edges.items():
            uf_old.union(i, j)

        # --- 3) apply join/detach (embodiment)
        positions = np.vstack([a.pos for a in self.agents])
        _neigh = compute_neighbors_torus(positions, self.Rp, self.size)  # used in next step

        joined, detached = apply_join_detach(
            positions=positions,
            size=self.size,
            edges=self.edges,
            degrees=self.degrees,
            t=self.t,
            Rc=self.Rc,
            max_degree=self.max_degree,
            Tmin=self.Tmin,
            detach_base_p=self.detach_base_p,
            boreness=self.boreness,
            rng=self.rng,
        )

        # --- 4) new components + cluster ids
        uf_new = UnionFind(self.N)
        for (i, j), _e in self.edges.items():
            uf_new.union(i, j)
        roots, comps = uf_new.components()
        root_to_cid = {r: idx for idx, r in enumerate(sorted(comps.keys()))}
        for k in range(self.N):
            self.cluster_id[k] = root_to_cid[roots[k]]

        # --- 5) phase sync on merges
        if self.sync_mode == "anchor":
            for e in joined:
                if uf_old.find(e.i) != uf_old.find(e.j):
                    new_root = uf_new.find(e.i)
                    nodes = comps[new_root]
                    anchor = e.j  # deterministic anchor
                    anchor_phase = self.agents[anchor].phase
                    for n in nodes:
                        self.agents[n].phase = anchor_phase

        # --- 6) motion update (random walk + inertia)
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

        self._agents_writer.writerow(["t", "id", "x", "y", "vx", "vy", "phase", "degree", "cluster_id"])
        self._global_writer.writerow(["t", "mean_speed", "coherence", "n_clusters", "mean_cluster_size", "n_edges"])

    def _log(self) -> None:
        speeds: List[float] = []
        for a in self.agents:
            speeds.append(float(np.linalg.norm(a.vel)))
            self._agents_writer.writerow([
                self.t, a.idx, a.pos[0], a.pos[1], a.vel[0], a.vel[1],
                float(a.phase), int(self.degrees[a.idx]), int(self.cluster_id[a.idx])
            ])

        unique, counts = np.unique(self.cluster_id, return_counts=True)
        n_clusters = int(len(unique))
        mean_cluster_size = float(np.mean(counts)) if n_clusters > 0 else 0.0
        n_edges = int(len(self.edges))
        coh = self._coherence()

        self._global_writer.writerow([self.t, float(np.mean(speeds)), coh, n_clusters, mean_cluster_size, n_edges])

    def _close_logs(self) -> None:
        self._agents_f.close()
        self._global_f.close()