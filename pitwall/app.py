from __future__ import annotations

import random
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from pitwall.config import SimulationConfig
from pitwall.data_io import load_data
from pitwall.race import RaceSimulation
from pitwall.ui import run_race_ui


def _choose_track(console: Console, tracks: list) -> object:
    console.print("\n[bold]Wybierz tor:[/]")
    for i, t in enumerate(tracks, start=1):
        console.print(
            f"  {i:2d}. {t.name} (laps={t.laps}, pit~{t.avg_pit_stop_s}s, pace~{t.base_pace_s:.1f}s, rain={t.rain_chance_percent}%)"
        )

    while True:
        try:
            raw = console.input("Numer toru: ").strip()
        except EOFError:
            return tracks[0]
        try:
            idx = int(raw)
        except ValueError:
            continue
        if 1 <= idx <= len(tracks):
            return tracks[idx - 1]


def _shuffle_grid(drivers: list) -> None:
    random.shuffle(drivers)


def run() -> None:
    console = Console()
    config = SimulationConfig()
    rng = random.Random()

    data = load_data(Path(__file__).resolve().parent.parent / "data")

    track = _choose_track(console, data.tracks)

    # pogoda
    raining = rng.random() < (track.rain_chance_percent / 100.0)

    # grid
    drivers = [d for d in data.drivers]
    _shuffle_grid(drivers)

    sim = RaceSimulation(
        drivers=drivers,
        track_name=track.name,
        track_laps=track.laps,
        base_pace_s=track.base_pace_s,
        avg_pit_stop_s=track.avg_pit_stop_s,
        raining=raining,
        config=config,
        rng=rng,
    )

    # Przygotuj opony i strategię przed START.
    sim.prepare()

    console.print("\n[bold]Pogoda:[/] " + ("[cyan]SUCHO[/]" if not raining else "[blue]DESZCZ[/]"))

    table = Table(title="Ustawienie startowe (losowe) + strategia", show_lines=False)
    table.add_column("P", justify="right", width=3)
    table.add_column("Kierowca")
    table.add_column("Team")
    table.add_column("Start opony", justify="center")
    table.add_column("Strategia", justify="left")

    for i, d in enumerate(drivers, start=1):
        start_tire_value = d.tires.tire_type.value if d.tires else "-"
        start_tire = Text(
            start_tire_value,
            style={
                "SOFT": "red",
                "MEDIUM": "yellow",
                "HARD": "bright_white",
                "WET": "blue",
                "-": "dim",
            }.get(start_tire_value, "white"),
        )
        if raining:
            strategy = "WET (bez wymogu 2 mieszanek)"
        else:
            planned_lap = sim.planned_pit_lap_for(d.name)
            next_comp = d.pick_next_compound(False).value
            if planned_lap is None:
                strategy = f"Pit wg zużycia → {next_comp}"
            else:
                strategy = f"Pit ok. lap {planned_lap} → {next_comp}"

        table.add_row(str(i), d.name, d.team_name, start_tire, strategy)

    console.print("\n")
    console.print(table)

    run_race_ui(sim, config, rng)
