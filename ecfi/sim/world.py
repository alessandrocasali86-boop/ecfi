from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ecfi.sim.neighbors import compute_neighbors_torus, torus_delta
from ecfi.assembly.rules import apply_join_detach, Edge
from ecfi.assembly.components import UnionFind

from ecfi.cognition.intention import update_intention, beta_effective
from ecfi.cognition.objective import update_objective
from ecfi.signals.constraints import (
    ema_update,
    novelty_from_F,
    update_boreness,
    update_event_rate,
    compute_load,
)


@dataclass
class Agent:
    idx: int
    pos: np.ndarray  # (2,)
    vel: np.ndarray  # (2,)
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

        # cognition params
        self.tau_c = float(cfg["cognition"]["tau_c"])
        self.g = float(cfg["cognition"]["g"])
        self.alpha = float(cfg["cognition"]["alpha"])
        self.beta_I = float(cfg["cognition"]["beta_I"])
        self.beta_C = float(cfg["cognition"]["beta_C"])
        self.beta_N = float(cfg["cognition"]["beta_N"])

        # objective params
        w_init = np.array(cfg["objective"]["init_weights"], dtype=float)
        self.w_init = w_init / max(1e-12, float(np.sum(w_init)))
        self.obj_update_rate = float(cfg["objective"]["update_rate"])
        self.obj_relax_rate = float(cfg["objective"]["relax_rate"])

        # constraints params
        self.features_ema = float(cfg["constraints"]["features_ema"])
        self.lam = float(cfg["constraints"]["lambda"])
        self.eta = float(cfg["constraints"]["eta"])
        self.b_max = float(cfg["constraints"]["b_max"])
        self.c_max = float(cfg["constraints"]["c_max"])
        self.event_ema = float(cfg["constraints"]["event_ema"])
        self.gamma = np.array(cfg["constraints"]["gamma"], dtype=float)

        # policy params
        self.k_align = float(cfg["policy"]["k_align"])
        self.k_cohesion = float(cfg["policy"]["k_cohesion"])
        self.k_sep = float(cfg["policy"]["k_sep"])
        self.R_sep = float(cfg["policy"]["R_sep"])
        self.damp = float(cfg["policy"]["damp"])

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

        # cognition state
        self.weights = np.tile(self.w_init[None, :], (self.N, 1))  # (N,3)
        self.omega = np.zeros((self.N, 3), dtype=float)            # (N,3)
        self.F = np.zeros((self.N, 3), dtype=float)                # (N,3)

        self.novelty = np.zeros(self.N, dtype=float)
        self.boreness = np.zeros(self.N, dtype=float)
        self.event_rate = np.zeros(self.N, dtype=float)
        self.load = np.zeros(self.N, dtype=float)

        # per-step cached signals for logging
        self.cluster_sizes = np.ones(self.N, dtype=float)
        self.local_coh = np.zeros(self.N, dtype=float)

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
        # --- 1) oscillator update + firing events
        fired = np.zeros(self.N, dtype=float)
        for a in self.agents:
            noise = self.rng.normal(0.0, self.phase_noise_sigma) * np.sqrt(self.dt)
            a.phase += self.omega0 * self.dt + noise
            if a.phase >= 1.0:
                a.phase -= 1.0
                fired[a.idx] = 1.0
            elif a.phase < 0.0:
                a.phase += 1.0

        # --- 2) pre-join components (to detect merges)
        uf_old = UnionFind(self.N)
        for (i, j), _e in self.edges.items():
            uf_old.union(i, j)

        # --- 3) neighbors + join/detach
        positions = np.vstack([a.pos for a in self.agents])
        vels = np.vstack([a.vel for a in self.agents])

        neigh = compute_neighbors_torus(positions, self.Rp, self.size)

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
                    anchor = e.j
                    anchor_phase = self.agents[anchor].phase
                    for n in nodes:
                        self.agents[n].phase = anchor_phase

        # --- 6) cluster sizes per agent
        cluster_sizes = np.zeros(self.N, dtype=float)
        for root, nodes in comps.items():
            sz = float(len(nodes))
            for n in nodes:
                cluster_sizes[n] = sz
        self.cluster_sizes = cluster_sizes

        # --- 7) local coherence per agent (self + neighbors)
        phases = np.array([a.phase for a in self.agents], dtype=float)
        local_coh = np.zeros(self.N, dtype=float)
        for k in range(self.N):
            idxs = [k] + list(neigh[k])
            z = np.exp(2j * np.pi * phases[idxs])
            local_coh[k] = float(np.abs(np.mean(z)))
        self.local_coh = local_coh

        # --- 8) features x, neighbor sums
        x = np.column_stack([self.degrees.astype(float), cluster_sizes, local_coh])  # (N,3)

        neigh_sum_x = np.zeros((self.N, 3), dtype=float)
        neigh_sizes = np.array([len(neigh[k]) for k in range(self.N)], dtype=float)
        for k in range(self.N):
            if neigh[k]:
                neigh_sum_x[k] = np.sum(x[neigh[k]], axis=0)

        # --- 9) intention update
        beta_eff = beta_effective(self.weights, self.beta_I, self.beta_C, self.beta_N)
        self.omega = update_intention(
            omega=self.omega,
            x=x,
            neigh_sum_x=neigh_sum_x,
            beta_eff=beta_eff,
            alpha=self.alpha,
            tau_c=self.tau_c,
            g=self.g,
            dt=self.dt,
        )

        # --- 10) novelty from EMA summary
        F_prev = self.F.copy()
        self.F = ema_update(self.F, x, self.features_ema)
        self.novelty = novelty_from_F(F_prev, self.F)

        # --- 11) events -> event rate
        events = fired.copy()
        for e in joined:
            events[e.i] += 1.0
            events[e.j] += 1.0
        for e in detached:
            events[e.i] += 1.0
            events[e.j] += 1.0
        self.event_rate = update_event_rate(self.event_rate, events, self.event_ema)

        # --- 12) boreness + load
        self.boreness = update_boreness(self.boreness, self.novelty, self.lam, self.eta)
        self.load = compute_load(neigh_sizes, self.degrees, self.event_rate, self.novelty, self.gamma)

        # --- 13) objective update
        self.weights = update_objective(
            weights=self.weights,
            w_init=self.w_init,
            b=self.boreness,
            c=self.load,
            b_max=self.b_max,
            c_max=self.c_max,
            update_rate=self.obj_update_rate,
            relax_rate=self.obj_relax_rate,
        )

        # --- 14) steering policy (alignment/cohesion/separation modulated by weights + intention)
        omega_norm = np.linalg.norm(self.omega, axis=1)
        s = np.tanh(omega_norm)  # in [0,1]
        u = np.zeros((self.N, 2), dtype=float)

        for k in range(self.N):
            if not neigh[k]:
                continue

            vbar = np.mean(vels[neigh[k]], axis=0)
            nv = float(np.linalg.norm(vbar))
            vdir = vbar / (nv + 1e-12)

            disp = np.zeros(2, dtype=float)
            for j in neigh[k]:
                disp += torus_delta(positions[k], positions[j], self.size)
            disp /= float(len(neigh[k]))
            nd = float(np.linalg.norm(disp))
            cdir = disp / (nd + 1e-12)

            sep = np.zeros(2, dtype=float)
            for j in neigh[k]:
                d = torus_delta(positions[k], positions[j], self.size)
                dist = float(np.hypot(d[0], d[1]))
                if dist < self.R_sep and dist > 1e-12:
                    sep -= d / (dist * dist)
            ns = float(np.linalg.norm(sep))
            if ns > 1e-12:
                sep = sep / ns

            wI, wC, wN = self.weights[k]
            align_term = (wI - wC) * vdir
            coh_term = (wI - wN) * cdir

            u[k] = s[k] * (self.k_align * align_term + self.k_cohesion * coh_term) + self.k_sep * sep

        # --- 15) integrate motion (with damping + noise)
        for a in self.agents:
            k = a.idx
            a.vel = a.vel + u[k] * self.dt - self.damp * a.vel * self.dt

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

        self._agents_writer.writerow([
            "t", "id", "x", "y", "vx", "vy", "phase",
            "degree", "cluster_id", "cluster_size", "local_coh",
            "novelty", "boreness", "load",
            "wI", "wC", "wN", "omega_norm",
        ])

        self._global_writer.writerow([
            "t", "mean_speed", "coherence",
            "n_clusters", "mean_cluster_size", "n_edges",
            "mean_novelty", "mean_boreness", "mean_load",
        ])

    def _log(self) -> None:
        speeds: List[float] = []
        for a in self.agents:
            speeds.append(float(np.linalg.norm(a.vel)))
            k = a.idx
            self._agents_writer.writerow([
                self.t, k, a.pos[0], a.pos[1], a.vel[0], a.vel[1], float(a.phase),
                int(self.degrees[k]), int(self.cluster_id[k]),
                float(self.cluster_sizes[k]), float(self.local_coh[k]),
                float(self.novelty[k]), float(self.boreness[k]), float(self.load[k]),
                float(self.weights[k, 0]), float(self.weights[k, 1]), float(self.weights[k, 2]),
                float(np.linalg.norm(self.omega[k])),
            ])

        unique, counts = np.unique(self.cluster_id, return_counts=True)
        n_clusters = int(len(unique))
        mean_cluster_size = float(np.mean(counts)) if n_clusters > 0 else 0.0
        n_edges = int(len(self.edges))
        coh = self._coherence()

        mean_nov = float(np.mean(self.novelty))
        mean_bor = float(np.mean(self.boreness))
        mean_load = float(np.mean(self.load))

        self._global_writer.writerow([
            self.t,
            float(np.mean(speeds)),
            coh,
            n_clusters,
            mean_cluster_size,
            n_edges,
            mean_nov,
            mean_bor,
            mean_load,
        ])

    def _close_logs(self) -> None:
        self._agents_f.close()
        self._global_f.close()