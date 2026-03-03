from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from music21 import meter, note, stream, tempo


# -----------------------------
# Data model
# -----------------------------
@dataclass(frozen=True)
class Event:
    t: float          # seconds
    part: int         # 0..P-1
    midi: int         # MIDI pitch
    ql: float         # duration in quarterLength
    vel: int          # 1..127


# -----------------------------
# Utilities
# -----------------------------
def _scale_major_pentatonic(root: int) -> List[int]:
    # intervals in semitones (major pentatonic): 0,2,4,7,9
    return [root + i for i in (0, 2, 4, 7, 9)]


def _clip_int(x: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(x))))


def _quantize_to_grid(t_sec: float, bpm: float, grid_div: int) -> float:
    """
    Quantize a time in seconds to a rhythmic grid, expressed in quarterLength offsets.

    grid_div = 4  -> 16th notes (since quarter is 1, 1/4 = 16th)
    """
    sec_per_quarter = 60.0 / bpm
    ql = t_sec / sec_per_quarter
    step = 1.0 / grid_div
    return round(round(ql / step) * step, 6)


# -----------------------------
# Event extraction
# -----------------------------
def extract_fire_events(
    agents_csv: Path,
    dt: float,
    bpm: float,
    grid_div: int,
    parts: int,
    root: int,
    max_events: int,
) -> List[Event]:
    """
    Fire detection: for each agent id, if phase(t) < phase(t-1) then fire at time t*dt.
    """
    scale = _scale_major_pentatonic(root)
    last_phase: Dict[int, float] = {}
    events: List[Event] = []

    with agents_csv.open("r", newline="") as f:
        r = csv.DictReader(f)
        required = {"t", "id", "phase", "degree", "cluster_size", "load"}
        missing = required.difference(r.fieldnames or [])
        if missing:
            raise ValueError(f"agents.csv missing columns: {sorted(missing)}")

        for row in r:
            t_step = int(float(row["t"]))
            k = int(float(row["id"]))
            phase = float(row["phase"]) % 1.0
            deg = int(float(row["degree"]))
            csize = int(float(row["cluster_size"]))
            load = float(row["load"])

            prev = last_phase.get(k)
            last_phase[k] = phase
            if prev is None:
                continue

            # wrap -> fire
            if phase < prev:
                # gate: do not play if isolated (degree == 0)
                if deg <= 0:
                    continue

                t_sec = t_step * dt
                ql_offset = _quantize_to_grid(t_sec, bpm=bpm, grid_div=grid_div)
                ql_offset = round(ql_offset, 6)

                # pitch: id-based stable mapping + "virtual slot" idea (deg affects index)
                slot = (len(events) + k) % max(1, deg)
                midi = scale[(k + slot) % len(scale)] + 12 * (k % 2)  # simple octave alternation

                # duration: depends on cluster size (bigger -> longer), bounded
                # map csize in [1..N] to ql in [0.25..1.5]
                ql = 0.25 + min(1.25, 0.03 * max(0, csize - 1))
                # Quantize duration to notatable values (same grid as offsets)
                step = 1.0 / grid_div
                ql = max(step, round(ql / step) * step)
                ql = round(ql, 6)

                # velocity: decreases with load, bounded
                vel = _clip_int(110 - 10.0 * load, 25, 115)

                part = k % parts
                events.append(Event(t=ql_offset, part=part, midi=midi, ql=ql, vel=vel))

                if len(events) >= max_events:
                    break

    # Ensure events are time-ordered within each part insertion
    events.sort(key=lambda e: (e.part, e.t))
    return events


# -----------------------------
# Rendering (music21)
# -----------------------------
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
    ap = argparse.ArgumentParser(description="Render ecfi agents.csv to MIDI + MusicXML via music21 (MVP).")
    ap.add_argument("--run_dir", type=str, default="outputs/run", help="Directory containing agents.csv.")
    ap.add_argument("--out_mid", type=str, default="outputs/run/sonification.mid", help="Output MIDI path.")
    ap.add_argument("--out_xml", type=str, default="outputs/run/sonification.musicxml", help="Output MusicXML path.")
    ap.add_argument("--dt", type=float, default=0.02, help="Simulation dt (seconds). If unsure, use config_resolved.json.")
    ap.add_argument("--bpm", type=float, default=120.0, help="Tempo for quantization and score.")
    ap.add_argument("--grid_div", type=int, default=4, help="Grid division per quarter (4 -> 16ths).")
    ap.add_argument("--parts", type=int, default=4, help="Number of parts in the score.")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI note (60 = C4).")
    ap.add_argument("--max_events", type=int, default=2000, help="Cap events to keep score readable.")
    ap.add_argument("--time_signature", type=str, default="4/4", help="Time signature for the score.")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    agents_csv = run_dir / "agents.csv"
    if not agents_csv.exists():
        raise FileNotFoundError(f"Missing {agents_csv}. Run a simulation first.")

    events = extract_fire_events(
        agents_csv=agents_csv,
        dt=args.dt,
        bpm=args.bpm,
        grid_div=args.grid_div,
        parts=args.parts,
        root=args.root,
        max_events=args.max_events,
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


if __name__ == "__main__":
    main()
