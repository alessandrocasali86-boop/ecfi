from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

from music21 import meter, note, stream, tempo


@dataclass(frozen=True)
class Event:
    t: float          # quarterLength offset
    part: int         # 0..P-1
    midi: int         # MIDI pitch
    ql: float         # duration in quarterLength
    vel: int          # 1..127


def _scale_major_pentatonic(root: int) -> List[int]:
    # intervals in semitones (major pentatonic): 0,2,4,7,9
    return [root + i for i in (0, 2, 4, 7, 9)]


def _clip_int(x: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(x))))


def _quantize_to_grid(t_sec: float, bpm: float, grid_div: int) -> float:
    """
    Quantize a time in seconds to a rhythmic grid, expressed in quarterLength offsets.
    grid_div = 4 -> 16th notes (since quarter is 1, 1/4 = 16th)
    """
    sec_per_quarter = 60.0 / bpm
    ql = t_sec / sec_per_quarter
    step = 1.0 / grid_div
    return round(round(ql / step) * step, 6)


def _parse_division_set(spec: str) -> List[Tuple[int, int]]:
    """
    Parse a comma-separated list like: "1:1,1:2,1:3,1:4,2:3"
    Returns list of (c,b) pairs.
    """
    out: List[Tuple[int, int]] = []
    for tok in (spec or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if ":" not in tok:
            raise ValueError(f"Invalid division token (expected c:b): {tok}")
        c_str, b_str = tok.split(":", 1)
        c = int(c_str)
        b = int(b_str)
        if c <= 0 or b <= 0:
            raise ValueError(f"Division must be positive: {tok}")
        out.append((c, b))
    if not out:
        out = [(1, 1)]
    return out


def _choose_division_for_agent(k: int, division_set: List[Tuple[int, int]], seed: int) -> Tuple[int, int]:
    """
    Deterministic per-agent assignment: stable across file order.
    """
    rng = random.Random(seed + k)
    return rng.choice(division_set)


def _division_to_thin_factor(c: int, b: int) -> int:
    """
    THIN approximation: keep one event every m wraps.
    m ~= round(c/b), clamped to >= 1.
    Note: thinning cannot produce >1 event per cycle (wrap).
    """
    return max(1, int(round(c / b)))


def _cluster_transpose_semitones(cluster_id: int, mode: str) -> int:
    """
    Convert cluster_id to a pitch-class transposition.
    - none: 0
    - fifths: +7 * cluster_id mod 12 (circle-of-fifths walk)
    """
    if mode == "none":
        return 0
    if mode == "fifths":
        return (7 * (cluster_id % 12)) % 12
    raise ValueError(f"Unknown cluster_transpose mode: {mode}")


def _duration_from_cluster_size(cluster_size: int, grid_div: int) -> float:
    # base rule: bigger cluster -> longer notes, then quantize to notatable values
    ql = 0.25 + min(1.25, 0.03 * max(0, cluster_size - 1))
    step = 1.0 / grid_div
    ql = max(step, round(ql / step) * step)
    return round(ql, 6)


def _pitch_from_state(scale: List[int], k: int, slot: int, cluster_id: int, cluster_transpose: str) -> int:
    base = scale[(k + slot) % len(scale)] + 12 * (k % 2)  # simple octave alternation
    transp = _cluster_transpose_semitones(cluster_id, mode=cluster_transpose)
    return base + transp


def _events_thin_from_csv(
    agents_csv: Path,
    dt: float,
    bpm: float,
    grid_div: int,
    parts: int,
    root: int,
    max_events: int,
    division_set: List[Tuple[int, int]],
    division_seed: int,
    cluster_transpose: str,
) -> List[Event]:
    """
    Current MVP: wrap detection + wrap-thinning (approximation of c:b).
    """
    scale = _scale_major_pentatonic(root)
    last_phase: Dict[int, float] = {}
    wrap_count: Dict[int, int] = {}
    thin_factor: Dict[int, int] = {}
    events: List[Event] = []

    with agents_csv.open("r", newline="") as f:
        r = csv.DictReader(f)
        required = {"t", "id", "phase", "degree", "cluster_id", "cluster_size", "load"}
        missing = required.difference(r.fieldnames or [])
        if missing:
            raise ValueError(f"agents.csv missing columns: {sorted(missing)}")

        for row in r:
            t_step = int(float(row["t"]))
            k = int(float(row["id"]))
            phase = float(row["phase"]) % 1.0
            deg = int(float(row["degree"]))
            cluster_id = int(float(row["cluster_id"]))
            csize = int(float(row["cluster_size"]))
            load = float(row["load"])

            prev = last_phase.get(k)
            last_phase[k] = phase
            if prev is None:
                continue

            if phase < prev:
                wc = wrap_count.get(k, 0) + 1
                wrap_count[k] = wc

                if k not in thin_factor:
                    c, b = _choose_division_for_agent(k, division_set, division_seed)
                    thin_factor[k] = _division_to_thin_factor(c, b)

                m_k = thin_factor[k]
                if (wc % m_k) != 0:
                    continue

                if deg <= 0:
                    continue

                t_sec = t_step * dt
                ql_offset = _quantize_to_grid(t_sec, bpm=bpm, grid_div=grid_div)

                slot = (wc + k) % max(1, deg)
                midi = _pitch_from_state(scale, k, slot, cluster_id, cluster_transpose)

                ql = _duration_from_cluster_size(csize, grid_div)
                vel = _clip_int(110 - 10.0 * load, 25, 115)

                part = k % parts
                events.append(Event(t=ql_offset, part=part, midi=midi, ql=ql, vel=vel))

                if len(events) >= max_events:
                    break

    events.sort(key=lambda e: (e.t, e.part))
    return events


def _build_faithful_schedule(
    agents_csv: Path,
    dt: float,
    division_set: List[Tuple[int, int]],
    division_seed: int,
) -> Dict[int, Dict[int, List[float]]]:
    """
    Faithful Lucas-like c:b schedule (offline subdivision).

    1) Detect wrap steps per agent from phase(t) < phase(t-1).
    2) For each agent k with rule (c,b), take non-overlapping blocks of c cycles:
       [wrap[i], wrap[i+c]] and generate b event times inside:
         t = t0 + m*(t1-t0)/b, m=0..b-1.
    3) Return mapping: agent -> step -> list of event times in seconds (can be multiple per step).
    """
    last_phase: Dict[int, float] = {}
    wraps: Dict[int, List[int]] = defaultdict(list)

    with agents_csv.open("r", newline="") as f:
        r = csv.DictReader(f)
        required = {"t", "id", "phase"}
        missing = required.difference(r.fieldnames or [])
        if missing:
            raise ValueError(f"agents.csv missing columns: {sorted(missing)}")

        for row in r:
            t_step = int(float(row["t"]))
            k = int(float(row["id"]))
            phase = float(row["phase"]) % 1.0
            prev = last_phase.get(k)
            last_phase[k] = phase
            if prev is None:
                continue
            if phase < prev:
                wraps[k].append(t_step)

    schedule: Dict[int, Dict[int, List[float]]] = {}
    for k, wsteps in wraps.items():
        if len(wsteps) < 2:
            continue

        c, b = _choose_division_for_agent(k, division_set, division_seed)
        by_step: Dict[int, List[float]] = defaultdict(list)

        i = 0
        while (i + c) < len(wsteps):
            start_step = wsteps[i]
            end_step = wsteps[i + c]
            start_sec = start_step * dt
            end_sec = end_step * dt
            if end_sec > start_sec:
                dur = end_sec - start_sec
                for m in range(b):
                    t_sec = start_sec + (m / b) * dur
                    step = int(round(t_sec / dt))
                    by_step[step].append(t_sec)
            i += c

        schedule[k] = dict(by_step)

    return schedule


def _events_faithful_from_csv(
    agents_csv: Path,
    dt: float,
    bpm: float,
    grid_div: int,
    parts: int,
    root: int,
    max_events: int,
    division_set: List[Tuple[int, int]],
    division_seed: int,
    cluster_transpose: str,
) -> List[Event]:
    """
    Faithful Lucas-like c:b:
    - build intra-cycle schedule from wraps (offline)
    - second pass: sample agent state at nearest timestep for each scheduled event
    """
    scale = _scale_major_pentatonic(root)
    schedule = _build_faithful_schedule(agents_csv, dt, division_set, division_seed)
    ev_count: Dict[int, int] = defaultdict(int)

    events: List[Event] = []

    with agents_csv.open("r", newline="") as f:
        r = csv.DictReader(f)
        required = {"t", "id", "degree", "cluster_id", "cluster_size", "load"}
        missing = required.difference(r.fieldnames or [])
        if missing:
            raise ValueError(f"agents.csv missing columns: {sorted(missing)}")

        for row in r:
            t_step = int(float(row["t"]))
            k = int(float(row["id"]))

            by_step = schedule.get(k)
            if not by_step:
                continue
            times_here = by_step.get(t_step)
            if not times_here:
                continue

            deg = int(float(row["degree"]))
            if deg <= 0:
                continue

            cluster_id = int(float(row["cluster_id"]))
            csize = int(float(row["cluster_size"]))
            load = float(row["load"])

            for t_sec in times_here:
                ql_offset = _quantize_to_grid(t_sec, bpm=bpm, grid_div=grid_div)

                idx = ev_count[k]
                ev_count[k] = idx + 1

                slot = (idx + k) % max(1, deg)
                midi = _pitch_from_state(scale, k, slot, cluster_id, cluster_transpose)

                ql = _duration_from_cluster_size(csize, grid_div)
                vel = _clip_int(110 - 10.0 * load, 25, 115)

                part = k % parts
                events.append(Event(t=ql_offset, part=part, midi=midi, ql=ql, vel=vel))

                if len(events) >= max_events:
                    break
            if len(events) >= max_events:
                break

    events.sort(key=lambda e: (e.t, e.part))
    return events


def render_to_m21(
    events: List[Event],
    bpm: float,
    time_signature: str,
    parts: int,
) -> stream.Score:
    s = stream.Score(id="ecfi_sonification")
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature(time_signature))

    part_streams: List[stream.Part] = []
    for i in range(parts):
        p = stream.Part(id=f"P{i}")
        p.partName = f"Part {i+1}"
        part_streams.append(p)
        s.append(p)

    for e in events:
        n = note.Note(e.midi)
        n.quarterLength = e.ql
        n.volume.velocity = e.vel
        part_streams[e.part].insert(e.t, n)

    return s


def main() -> None:
    ap = argparse.ArgumentParser(description="Render ecfi agents.csv to MIDI + MusicXML via music21.")
    ap.add_argument("--run_dir", type=str, default="outputs/run", help="Directory containing agents.csv.")
    ap.add_argument("--out_mid", type=str, default="outputs/run/sonification.mid", help="Output MIDI path.")
    ap.add_argument("--out_xml", type=str, default="outputs/run/sonification.musicxml", help="Output MusicXML path.")
    ap.add_argument("--dt", type=float, default=0.02, help="Simulation dt (seconds).")
    ap.add_argument("--bpm", type=float, default=120.0, help="Tempo for quantization and score.")
    ap.add_argument("--grid_div", type=int, default=4, help="Grid division per quarter (4 -> 16ths).")
    ap.add_argument("--parts", type=int, default=4, help="Number of parts in the score.")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI note (60 = C4).")
    ap.add_argument("--max_events", type=int, default=1200, help="Cap events to keep score readable.")
    ap.add_argument("--time_signature", type=str, default="4/4", help="Time signature for the score.")

    ap.add_argument("--division_mode", type=str, default="thin", choices=["thin", "faithful"],
                    help="thin = wrap-thinning approximation; faithful = true c:b intra-cycle subdivision.")
    ap.add_argument("--division_set", type=str, default="1:1,2:1,3:1,4:1",
                    help="Comma list of c:b division rules.")
    ap.add_argument("--division_seed", type=int, default=0, help="Seed for deterministic per-agent division assignment.")
    ap.add_argument("--cluster_transpose", type=str, default="fifths", choices=["none", "fifths"],
                    help="Cluster-based transposition mode.")

    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    agents_csv = run_dir / "agents.csv"
    if not agents_csv.exists():
        raise FileNotFoundError(f"Missing {agents_csv}. Run a simulation first.")

    division_set = _parse_division_set(args.division_set)

    if args.division_mode == "thin":
        events = _events_thin_from_csv(
            agents_csv=agents_csv,
            dt=args.dt,
            bpm=args.bpm,
            grid_div=args.grid_div,
            parts=args.parts,
            root=args.root,
            max_events=args.max_events,
            division_set=division_set,
            division_seed=args.division_seed,
            cluster_transpose=args.cluster_transpose,
        )
    else:
        events = _events_faithful_from_csv(
            agents_csv=agents_csv,
            dt=args.dt,
            bpm=args.bpm,
            grid_div=args.grid_div,
            parts=args.parts,
            root=args.root,
            max_events=args.max_events,
            division_set=division_set,
            division_seed=args.division_seed,
            cluster_transpose=args.cluster_transpose,
        )

    score = render_to_m21(
        events=events,
        bpm=args.bpm,
        time_signature=args.time_signature,
        parts=args.parts,
    )
    score.makeMeasures(inPlace=True)

    out_mid = Path(args.out_mid)
    out_xml = Path(args.out_xml)
    out_mid.parent.mkdir(parents=True, exist_ok=True)
    out_xml.parent.mkdir(parents=True, exist_ok=True)

    score.write("midi", fp=str(out_mid))
    score.write("musicxml", fp=str(out_xml))

    print(f"Wrote MIDI: {out_mid}")
    print(f"Wrote MusicXML: {out_xml}")
    print(f"Events rendered: {len(events)}")
    print(f"division_mode: {args.division_mode}  division_set: {args.division_set}  division_seed: {args.division_seed}  cluster_transpose: {args.cluster_transpose}")


if __name__ == "__main__":
    main()
