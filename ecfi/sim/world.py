# ecfi/sim/world.py
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from ecfi.sim.neighbors import compute_neighbors_torus
from ecfi.sim.oscillator import advance_phases, detect_firing, order_parameter
from ecfi.assembly.rules import apply_join_detach, Edge
from ecfi.assembly.components import UnionFind


@dataclass
class Agent:
    idx: int
    pos: np.ndarray  # shape (2,)
    vel: np.ndarray  # shape (2,)


class World:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg

        # --- sim ---
        self.dt = float(cfg["sim"]["dt"])
        self.steps = int(cfg["sim"]["steps"])
        self.t = 0

        # --- env ---
        self.domain = str(cfg["env"]["domain"])
        self.size = np.array(cfg["env"]["size"], dtype=float)

        # --- agents ---
        self.N = int(cfg["agents"]["N"])
        self.vmax = float(cfg["agents"]["vmax"])
        self.noise_sigma = float(cfg["agents"]["noise_sigma"])

        # --- neighbors / assembly ---
        self.Rp = float(cfg["neighbors"]["Rp"])
        self.Rc = float(cfg["assembly"]["Rc"])
        self.max_degree = int(cfg["assembly"]["max_degree"])
        self.Tmin = int(cfg["assembly"]["Tmin"])
        self.detach_base_p = float(cfg["assembly"]["detach_base_p"])

        # --- oscillators ---
        osc_cfg = cfg.get("osc", {})
        self.omega0 = float(osc_cfg.get("omega0", 0.2))
        self.pulse_kick = float(osc_cfg.get("pulse_kick", 0.0))
        self.sync_mode = str(osc_cfg.get("sync_mode", "anchor"))  # anchor | mean

        # --- RNG ---
        self.seed = int(cfg.get("seed", 0))
        self.rng = np.random.default_rng(self.seed)

        # --- logging ---
        self.out_dir = Path(cfg["logging"]["out_dir"])
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_every = int(cfg["logging"]["every"])

        # --- state ---
        self.agents: List[Agent] = self._init_agents()

        # Assembly state
        self.edges: Dict[Tuple[int, int], Edge] = {}
        self.degrees = np.zeros(self.N, dtype=int)
        self.cluster_id = np.full(self.N, -1, dtype=int)

        # Placeholder boreness (per ora zero; poi la renderemo dinamica)
        self.boreness = np.zeros(self.N, dtype=float)

        # Oscillator state
        self.phi = self.rng.random(self.N).astype(float)  # phases in [0,1)
        self.fired = np.zeros(self.N, dtype=int)
        self.phase_r = 0.0

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
        return np.mod(pos, self.size)

    def _update_motion(self) -> None:
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

    def _sync_component_phases_anchor(self, members: List[int]) -> None:
        anchor = members[0]
        self.phi[np.array(members, dtype=int)] = self.phi[anchor]

    def _sync_component_phases_mean(self, members: List[int]) -> None:
        idx = np.array(members, dtype=int)
        angles = 2.0 * np.pi * self.phi[idx]
        z = np.exp(1j * angles).mean()
        mean_angle = float(np.angle(z))
        mean_phi = (mean_angle / (2.0 * np.pi)) % 1.0
        self.phi[idx] = mean_phi

    def _update_assembly_and_clusters(self) -> None:
        positions = np.vstack([a.pos for a in self.agents])

        # Proximity neighbors (Rp) – per ora non serve direttamente alle join,
        # ma lo teniamo perché sarà utile per cognition / segnali.
        _neigh = compute_neighbors_torus(positions, self.Rp, self.size)

        # --- components BEFORE join/detach ---
        uf_before = UnionFind(self.N)
        for (i, j) in self.edges.keys():
            uf_before.union(i, j)
        _, comps_before = uf_before.components()

        # Join / detach (Rc)
        apply_join_detach(
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

        # --- components AFTER join/detach ---
        uf_after = UnionFind(self.N)
        for (i, j) in self.edges.keys():
            uf_after.union(i, j)

        roots_after, comps_after = uf_after.components()

        # --- sync on merges (if enabled) ---
        # A merge occurred if number of components decreased.
        if len(comps_after) < len(comps_before) and len(comps_after) > 0:
            if self.sync_mode == "mean":
                for members in comps_after.values():
                    self._sync_component_phases_mean(members)
            else:
                for members in comps_after.values():
                    self._sync_component_phases_anchor(members)

        # cluster ids from AFTER
        root_to_cid = {r: idx for idx, r in enumerate(sorted(comps_after.keys()))}
        for k in range(self.N):
            self.cluster_id[k] = root_to_cid[roots_after[k]]

    def step(self) -> None:
        # advance time first, so everything is consistently stamped with this.t
        self.t += 1

        # 1) motion update
        self._update_motion()

        # 2) oscillator advance + firing
        advance_phases(self.phi, self.omega0, self.rng, jitter=0.0)
        fired_mask = detect_firing(self.phi, threshold=0.999)
        self.fired[:] = fired_mask.astype(int)

        # 3) assembly + cluster update based on new positions (may sync on merge)
        self._update_assembly_and_clusters()

        # 4) optional pulse coupling on assembly edges (light MVP)
        if self.pulse_kick > 0.0 and int(self.fired.sum()) > 0:
            for (i, j) in self.edges.keys():
                if self.fired[i] == 1:
                    self.phi[j] = (self.phi[j] + self.pulse_kick) % 1.0
                if self.fired[j] == 1:
                    self.phi[i] = (self.phi[i] + self.pulse_kick) % 1.0

        # 5) global coherence
        self.phase_r = order_parameter(self.phi)

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

        self._agents_writer.writerow(["t", "id", "x", "y", "vx", "vy", "degree", "cluster_id", "phi", "fired"])
        self._global_writer.writerow(["t", "mean_speed", "n_clusters", "mean_cluster_size", "n_edges", "phase_r"])

    def _log(self) -> None:
        speeds: List[float] = []

        for a in self.agents:
            speeds.append(float(np.linalg.norm(a.vel)))
            self._agents_writer.writerow(
                [
                    self.t,
                    a.idx,
                    float(a.pos[0]),
                    float(a.pos[1]),
                    float(a.vel[0]),
                    float(a.vel[1]),
                    int(self.degrees[a.idx]),
                    int(self.cluster_id[a.idx]),
                    float(self.phi[a.idx]),
                    int(self.fired[a.idx]),
                ]
            )

        unique, counts = np.unique(self.cluster_id, return_counts=True)
        n_clusters = int(len(unique))
        mean_cluster_size = float(np.mean(counts)) if n_clusters > 0 else 0.0
        n_edges = int(len(self.edges))

        self._global_writer.writerow(
            [
                self.t,
                float(np.mean(speeds)) if speeds else 0.0,
                n_clusters,
                mean_cluster_size,
                n_edges,
                float(self.phase_r),
            ]
        )

    def _close_logs(self) -> None:
        self._agents_f.close()
        self._global_f.close()