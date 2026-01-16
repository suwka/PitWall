from __future__ import annotations

import random
import time
from collections import deque

from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pitwall.config import SimulationConfig
from pitwall.models import Driver, DriverStatus
from pitwall.race import RaceEvent, RaceSimulation


def _fmt_time(seconds: float) -> str:
    if seconds <= 0:
        return "0.0"
    m = int(seconds // 60)
    s = seconds - m * 60
    if m <= 0:
        return f"{s:.1f}s"
    return f"{m}:{s:04.1f}"


def _tire_text(tire_value: str) -> Text:
    style = {
        "SOFT": "red",
        "MEDIUM": "yellow",
        "HARD": "bright_white",
        "WET": "blue",
        "-": "dim",
    }.get(tire_value, "white")
    return Text(tire_value, style=style)


def _build_table(sim: RaceSimulation) -> Table:
    table = Table(
        title=f"{sim.track_name} | Lap {sim._lap_index} | Pogoda: {'DESZCZ' if sim.raining else 'SUCHO'}",
        box=box.SIMPLE_HEAVY,
        expand=True,
        show_lines=False,
    )
    table.add_column("P", justify="right", width=3)
    table.add_column("Kierowca", no_wrap=True)
    table.add_column("Team", no_wrap=True)
    table.add_column("Lap", justify="right", width=5)
    table.add_column("Total", justify="right", width=9)
    table.add_column("Last", justify="right", width=8)
    table.add_column("Opony", justify="center", width=7)
    table.add_column("Wear", justify="right", width=6)
    table.add_column("Pit", justify="right", width=3)
    table.add_column("Status", justify="center", width=8)

    drivers = sim.sorted_finished_and_running()
    for pos, d in enumerate(drivers, start=1):
        tires = d.tires
        tire_value = tires.tire_type.value if tires else "-"
        wear_txt = f"{(tires.wear_percent if tires else 0):.0f}%"

        status_style = "green" if d.status in (DriverStatus.RUNNING, DriverStatus.FINISHED) else "red"
        status = Text(d.status.value, style=status_style)

        name_style = "bold" if pos <= 3 else ""
        if d.status == DriverStatus.DNF:
            name_style = "dim"

        table.add_row(
            str(pos),
            Text(d.name, style=name_style),
            d.team_name,
            f"{d.lap}/{sim.track_laps}",
            _fmt_time(d.total_time_s),
            _fmt_time(d.last_lap_s),
            _tire_text(tire_value),
            wear_txt,
            str(d.pit_stops),
            status,
        )

    return table


def _build_log_panel(log_lines: deque[Text], title: str) -> Panel:
    text = Text()
    for line in list(log_lines)[-200:]:
        text.append(line)
        text.append("\n")
    return Panel(Align.left(text), title=title, border_style="cyan", box=box.SQUARE)


def _event_to_line(ev: RaceEvent) -> Text:
    label = {
        "PIT": "PIT",
        "DNF": "DNF",
        "OVT": "OVT",
        "INC": "INC",
        "COL": "COL",
        "RF": "RF",
        "FIN": "FIN",
        "END": "END",
        "FIA": "FIA",
    }.get(ev.kind, "INFO")

    color = {
        "PIT": "yellow",
        "DNF": "red",
        "OVT": "green",
        "INC": "magenta",
        "COL": "magenta",
        "RF": "red",
        "FIN": "cyan",
        "END": "cyan",
        "FIA": "cyan",
        "INFO": "white",
    }.get(label, "white")

    t = Text()
    t.append(f"{label}: ", style=color)
    t.append(ev.message)
    return t


def _wait_red_flag(console: Console, config: SimulationConfig, rng: random.Random) -> None:
    # Windows: pozwól wznowić Enterem bez blokowania odliczania.
    seconds = rng.uniform(config.red_flag_wait_min_s, config.red_flag_wait_max_s)
    end = time.monotonic() + seconds

    can_use_msvcrt = False
    try:
        import msvcrt  # type: ignore

        can_use_msvcrt = True
    except Exception:
        can_use_msvcrt = False

    console.print(
        f"[red bold]CZERWONA FLAGA[/] — wciśnij Enter aby wznowić lub poczekaj ~{seconds:.0f}s"
    )

    while time.monotonic() < end:
        remaining = end - time.monotonic()
        console.print(f"  wznowienie za: {remaining:4.1f}s", end="\r")
        time.sleep(0.12)
        if can_use_msvcrt:
            # Enter
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    break
    console.print("\n[green]WZNOWIONO[/]\n")


def run_race_ui(sim: RaceSimulation, config: SimulationConfig, rng: random.Random) -> None:
    console = Console()

    event_lines: deque[Text] = deque(maxlen=config.max_log_lines)
    overtake_lines: deque[Text] = deque(maxlen=config.max_log_lines)
    log_index = 0

    layout = Layout()
    layout.split_column(Layout(name="top", ratio=3), Layout(name="bottom", ratio=1))
    layout["bottom"].split_row(Layout(name="bottom_left"), Layout(name="bottom_right"))

    target_dt = 1.0 / max(1.0, config.ui_refresh_hz)

    # przelicznik: ile realnie „czekamy” na okrążenie (żeby całość trwała ~race_real_seconds)
    per_lap_sleep = max(0.02, config.race_real_seconds / max(1, sim.track_laps))

    console.clear()
    console.print(
        Panel(
            Text(
                "PitWall — F1 Simulation\n"
                "- ENTER: start\n"
                "- Podczas czerwonej flagi: ENTER = wznowienie\n",
                justify="left",
            ),
            title="Sterowanie",
            border_style="blue",
        )
    )
    try:
        console.input("Wciśnij Enter, aby wystartować…")
    except EOFError:
        pass

    sim.start()

    last_rf_seen = -1
    with console.status("Symulacja…"):
        from rich.live import Live

        with Live(layout, console=console, refresh_per_second=config.ui_refresh_hz, screen=True):
            while not sim.finished:
                # krok symulacji
                sim.step_lap()

                # eventy → log
                log_index, new_events = sim.pop_new_events(log_index)
                for ev in new_events:
                    line = _event_to_line(ev)
                    if ev.kind == "OVT":
                        overtake_lines.append(line)
                    else:
                        event_lines.append(line)

                # obsługa czerwonej flagi (jeśli padła w tym kroku)
                for ev in new_events:
                    if ev.kind == "RF" and log_index != last_rf_seen:
                        last_rf_seen = log_index
                        _wait_red_flag(console, config, rng)
                        break

                layout["top"].update(Panel(_build_table(sim), border_style="white"))
                layout["bottom_left"].update(_build_log_panel(overtake_lines, title="Wyprzedzenia"))
                layout["bottom_right"].update(_build_log_panel(event_lines, title="Zdarzenia"))

                time.sleep(per_lap_sleep)

    console.print("\n")
    console.print(Panel(_build_table(sim), title="WYNIKI", border_style="green"))

    dnfs = [d for d in sim.drivers if d.status == DriverStatus.DNF]
    if dnfs:
        console.print("\n[red bold]DNF:[/]")
        for d in dnfs:
            console.print(f"- {d.name} ({d.team_name})")
