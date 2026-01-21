from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from pitwall.config import SimulationConfig
from pitwall.models import Driver, DriverStatus, TireState, TireType


@dataclass
class RaceEvent:
    kind: str
    message: str


class FlagState(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class FlagObserver(Protocol):
    def on_flag_change(self, flag: FlagState) -> None: ...


@dataclass
class DriverRaceEffects:
    pace_multiplier: float = 1.0
    overtake_allowed: bool = True


class DriverFlagObserver:
    def __init__(self, *, effects: DriverRaceEffects, config: SimulationConfig) -> None:
        self._effects = effects
        self._config = config

    def on_flag_change(self, flag: FlagState) -> None:
        if flag == FlagState.YELLOW:
            self._effects.pace_multiplier = float(getattr(self._config, "yellow_pace_multiplier", 1.30))
            self._effects.overtake_allowed = False
        else:
            self._effects.pace_multiplier = 1.0
            self._effects.overtake_allowed = True


class PitStrategy(Protocol):
    def should_pit(self, sim: "RaceSimulation", driver: Driver, *, force_compound_change: bool) -> bool: ...

    def pick_next_compound(self, sim: "RaceSimulation", driver: Driver) -> TireType: ...


class DefaultPitStrategy:
    def should_pit(self, sim: "RaceSimulation", driver: Driver, *, force_compound_change: bool) -> bool:
        return driver.needs_pit() or force_compound_change

    def pick_next_compound(self, sim: "RaceSimulation", driver: Driver) -> TireType:
        return driver.pick_next_compound(sim.raining)


class NeutralizationPitStrategy(DefaultPitStrategy):
    def should_pit(self, sim: "RaceSimulation", driver: Driver, *, force_compound_change: bool) -> bool:
        if super().should_pit(sim, driver, force_compound_change=force_compound_change):
            return True

        # Konserwatywnie: pod żółtą flaga można „tani” pit, ale tylko jeśli
        # (a) zużycie już wyraźne i (b) pit nie kosztuje pozycji.
        if not sim.is_yellow_active():
            return False
        if sim.raining:
            return False
        tires = driver.ensure_tires()
        if tires.tire_type == TireType.WET:
            return False
        if tires.wear_percent > 35.0:
            return False

        pit_time_estimate = sim.avg_pit_stop_s + 1.0
        return sim.pit_wont_lose_position(driver, pit_time_estimate)


@dataclass(frozen=True)
class RestartMemento:
    running_order: list[str]


class RaceSimulation:
    def __init__(
        self,
        *,
        drivers: list[Driver],
        track_name: str,
        track_laps: int,
        base_pace_s: float,
        avg_pit_stop_s: float,
        raining: bool,
        config: SimulationConfig,
        pit_strategy: PitStrategy | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.drivers = drivers
        self.track_name = track_name
        self.track_laps = track_laps
        self.base_pace_s = base_pace_s
        self.avg_pit_stop_s = avg_pit_stop_s
        self.raining = raining
        self.config = config
        self.pit_strategy: PitStrategy = pit_strategy or NeutralizationPitStrategy()
        self.rng = rng or random.Random()

        self.events: list[RaceEvent] = []
        self.start_monotonic: float | None = None
        self.finished: bool = False

        # Zegar wyścigu (pauzowany na czerwonej fladze)
        self._paused_total_s: float = 0.0
        self._pause_started_monotonic: float | None = None

        # Flagi
        self.flag_state: FlagState = FlagState.GREEN
        self._red_flag_active: bool = False
        self._yellow_laps_remaining: int = 0

        # Observer: efekty flag na kierowcach
        self._driver_effects: dict[str, DriverRaceEffects] = {d.name: DriverRaceEffects() for d in self.drivers}
        self._flag_observers: list[FlagObserver] = [
            DriverFlagObserver(effects=self._driver_effects[d.name], config=self.config) for d in self.drivers
        ]

        # Memento: ustawienie restartu po czerwonej
        self._restart_memento: RestartMemento | None = None

        self._prepared: bool = False

        self._lap_index: int = 0
        self._last_positions: list[str] = []
        self._last_red_flag_lap: int = -10_000
        self._planned_pit_lap: dict[str, int] = {}

    def _set_flag(self, flag: FlagState) -> None:
        if self.flag_state == flag:
            return
        self.flag_state = flag
        for obs in self._flag_observers:
            obs.on_flag_change(flag)

    def is_yellow_active(self) -> bool:
        return self._yellow_laps_remaining > 0

    def pit_wont_lose_position(self, driver: Driver, pit_time_s: float) -> bool:
        running = self.sorted_running()
        idx = next((i for i, d in enumerate(running) if d.name == driver.name), None)
        if idx is None:
            return False

        # jeśli jest ostatni z RUNNING – nie ma komu stracić pozycji "z tyłu" w tej prostej ocenie
        if idx >= len(running) - 1:
            return True
        behind = running[idx + 1]
        gap_to_behind = behind.total_time_s - driver.total_time_s
        return gap_to_behind > (pit_time_s + 0.5)

    def prepare(self) -> None:
        if self._prepared:
            return

        for d in self.drivers:
            d.choose_start_tires(self.raining, self.rng)

        # Na sucho: zaplanuj prosty pit-stop w środku, aby spełnić wymóg 2 mieszanek.
        if not self.raining:
            min_lap = max(1, int(self.track_laps * 0.35))
            max_lap = max(min_lap, int(self.track_laps * 0.65))
            for d in self.drivers:
                planned = self.rng.randint(min_lap, max_lap)
                planned = min(planned, max(1, self.track_laps - 2))
                self._planned_pit_lap[d.name] = planned

        self._last_positions = [d.name for d in self.sorted_running()]
        self._prepared = True

    def start(self) -> None:
        if self.start_monotonic is None:
            self.start_monotonic = time.monotonic()
        self.prepare()

    def planned_pit_lap_for(self, driver_name: str) -> int | None:
        return self._planned_pit_lap.get(driver_name)

    def real_elapsed_s(self) -> float:
        if self.start_monotonic is None:
            return 0.0
        return time.monotonic() - self.start_monotonic

    def race_clock_elapsed_s(self) -> float:
        if self.start_monotonic is None:
            return 0.0
        paused = self._paused_total_s
        if self._pause_started_monotonic is not None:
            paused += time.monotonic() - self._pause_started_monotonic
        return max(0.0, time.monotonic() - self.start_monotonic - paused)

    def race_timer_s(self) -> float:
        """Timer wyścigu w skali `Total`.

        - dopóki nikt nie ukończył: timer = czas lidera (najmniejszy `total_time_s` w RUNNING)
        - gdy ktoś ukończy: timer = czas zwycięzcy (najmniejszy `total_time_s` w FINISHED) i pozostaje stały

        Dzięki temu timer jest spójny z kolumną `Total`.
        """

        finished_times = [d.total_time_s for d in self.drivers if d.status == DriverStatus.FINISHED]
        if finished_times:
            return min(finished_times)
        running_times = [d.total_time_s for d in self.drivers if d.status == DriverStatus.RUNNING]
        if running_times:
            return min(running_times)
        return 0.0

    def pause_clock(self) -> None:
        if self._pause_started_monotonic is None:
            self._pause_started_monotonic = time.monotonic()

    def resume_clock(self) -> None:
        if self._pause_started_monotonic is None:
            return
        self._paused_total_s += time.monotonic() - self._pause_started_monotonic
        self._pause_started_monotonic = None

    def clear_red_flag(self) -> None:
        self._red_flag_active = False
        if self.flag_state == FlagState.RED:
            self._set_flag(FlagState.GREEN)

        # Memento: zbij stawkę do restartu (tylko RUNNING), zachowując kolejność.
        if self._restart_memento is not None:
            order = self._restart_memento.running_order
            name_to_driver = {d.name: d for d in self.drivers}
            ordered_running = [name_to_driver[n] for n in order if n in name_to_driver and name_to_driver[n].status == DriverStatus.RUNNING]
            if ordered_running:
                leader_time = ordered_running[0].total_time_s
                gap_s = float(getattr(self.config, "restart_gap_s", 0.30))
                for i, d in enumerate(ordered_running):
                    d.total_time_s = leader_time + i * gap_s
                self._last_positions = [d.name for d in ordered_running]
            self._restart_memento = None

    def sorted_running(self) -> list[Driver]:
        running = [d for d in self.drivers if d.status == DriverStatus.RUNNING]
        return sorted(running, key=lambda x: x.total_time_s)

    def sorted_finished_and_running(self) -> list[Driver]:
        # klasyfikacja: FINISHED i RUNNING po czasie, DNF na końcu
        active = [d for d in self.drivers if d.status in (DriverStatus.RUNNING, DriverStatus.FINISHED)]
        dnfs = [d for d in self.drivers if d.status == DriverStatus.DNF]

        # W DNF: ci, którzy przejechali więcej okrążeń (odpadli później) mają być wyżej.
        # Najwcześniejszy DNF -> najniżej w tabeli.
        dnfs_sorted = sorted(dnfs, key=lambda x: (x.lap, x.total_time_s), reverse=True)
        return sorted(active, key=lambda x: x.total_time_s) + dnfs_sorted

    def _log(self, kind: str, message: str) -> None:
        self.events.append(RaceEvent(kind=kind, message=message))

    def pop_new_events(self, since: int) -> tuple[int, list[RaceEvent]]:
        # since = index
        if since < 0:
            since = 0
        new = self.events[since:]
        return len(self.events), new

    def _wear_per_lap(self, skill: int, tire_type: TireType) -> float:
        # z readme: wear_per_lap = 2.0 - (skill * 0.01)
        base = 2.0 - (skill * 0.01)
        base = max(0.6, base)
        if tire_type == TireType.WET:
            # wety zwykle trochę wolniej zużywają się w tej prostej symulacji
            return base * 0.85
        return base

    def _dnf_chance(self, skill: int) -> float:
        # z readme: 0.2% + (100-skill)*0.01% zmiana na 1% bo za malo dnf
        base = 0.01 + (100 - skill) * 0.0001
        # skalowanie do bardziej realistycznej liczby DNF w stawce
        scale = getattr(self.config, "dnf_chance_scale", 0.25)
        return base * float(scale)

    def _lap_time_s(self, driver: Driver, tires: TireState) -> float:
        # readme:
        # lap_time = base_pace - (skill * 0.007) - (car_score * 0.003)
        #           + random(-0.3, +0.3) + tire_penalty
        scatter = self.rng.uniform(-0.3, 0.3)
        tire_penalty = tires.penalty_s

        # Prosta różnica tempa mieszanek (na sucho):
        # SOFT najszybsze, MEDIUM pośrednie, HARD najwolniejsze.
        # Skala względem toru: % * base_pace_s.
        compound_step = 0
        if tires.tire_type == TireType.SOFT:
            compound_step = -1
        elif tires.tire_type == TireType.HARD:
            compound_step = 1
        compound_delta_pct = float(getattr(self.config, "tire_compound_delta_pct_per_step", 0.007))
        tire_penalty += self.base_pace_s * compound_delta_pct * compound_step
        wet_penalty = 0.0
        if self.raining and tires.tire_type != TireType.WET:
            wet_penalty = 8.0
        if (not self.raining) and tires.tire_type == TireType.WET:
            wet_penalty = 5.0

        return (
            self.base_pace_s
            - (driver.skill * 0.007)
            - (driver.car_score * 0.003)
            + scatter
            + tire_penalty
            + wet_penalty
        )

    def step_lap(self) -> None:
        if self.start_monotonic is None:
            raise RuntimeError("Race not started")

        if self.finished:
            return

        # Czerwona flaga zatrzymuje symulację (bez nabijania okrążeń).
        if self._red_flag_active:
            return

        # FIA: max 3h czasu wyścigu (tu: na podstawie minimalnego czasu w stawce)
        active_times = [d.total_time_s for d in self.drivers if d.status == DriverStatus.RUNNING]
        if active_times and min(active_times) >= self.config.race_sim_max_seconds:
            self._log("FIA", "Limit 3h przekroczony: wyścig zakończony (FIA).")
            self.finished = True
            return

        # globalny event: red flag (przed okrążeniem)
        if (
            (self._lap_index - self._last_red_flag_lap) >= self.config.red_flag_cooldown_laps
            and self.rng.random() < self.config.red_flag_chance_per_lap
        ):
            self._last_red_flag_lap = self._lap_index
            self._red_flag_active = True
            # Memento: zapamiętaj kolejność RUNNING na restart.
            self._restart_memento = RestartMemento(running_order=[d.name for d in self.sorted_running()])

            self._set_flag(FlagState.RED)

            rf_min = float(getattr(self.config, "red_flag_duration_min_minutes", 15.0))
            rf_max = float(getattr(self.config, "red_flag_duration_max_minutes", 30.0))
            rf_minutes = self.rng.uniform(rf_min, rf_max)
            rf_seconds = rf_minutes * 60.0

            # Doliczamy czas postoju do "Total" wszystkim nie-DNF.
            # To nie zmienia kolejności (wszyscy dostają tyle samo), ale zmienia timer i total.
            for d in self.drivers:
                if d.status in (DriverStatus.RUNNING, DriverStatus.FINISHED):
                    d.total_time_s += rf_seconds

            self._log(
                "RF",
                f"CZERWONA FLAGA! Postój ~{rf_minutes:.0f} min (doliczony do czasu wyścigu).",
            )
            return

        # start okrążenia
        yellow_active = self.is_yellow_active()
        if yellow_active:
            self._set_flag(FlagState.YELLOW)
            self._yellow_laps_remaining = max(0, self._yellow_laps_remaining - 1)
        else:
            self._set_flag(FlagState.GREEN)

        yellow_triggered = False
        yellow_reason: str | None = None
        self._lap_index += 1

        order_before = [d.name for d in self.sorted_running()] if yellow_active else []

        for d in self.drivers:
            if d.status != DriverStatus.RUNNING:
                continue

            if d.lap >= self.track_laps:
                d.status = DriverStatus.FINISHED
                continue

            tires = d.ensure_tires()

            # incydenty / kolizje
            if self.rng.random() < self.config.collision_chance_per_lap:
                # 50/50: DNF albo strata czasu
                dnf_prob = getattr(self.config, "collision_dnf_probability", 0.35)
                if self.rng.random() < float(dnf_prob):
                    yellow_triggered = True
                    if yellow_reason is None:
                        yellow_reason = f"DNF: {d.name}"
                    d.status = DriverStatus.DNF
                    self._log("DNF", f"{d.name} odpada po kolizji (DNF).")
                    continue
                else:
                    penalty = self.rng.uniform(3.0, 10.0)
                    d.total_time_s += penalty
                    self._log("COL", f"Kolizja: {d.name} traci {penalty:.1f}s.")

            if self.rng.random() < self.config.incident_chance_per_lap:
                loss = self.rng.uniform(0.4, 2.2)
                d.total_time_s += loss
                self._log("INC", f"Incydent na torze: {d.name} traci {loss:.1f}s.")

            # DNF
            if self.rng.random() < self._dnf_chance(d.skill):
                yellow_triggered = True
                if yellow_reason is None:
                    yellow_reason = f"DNF: {d.name}"
                d.status = DriverStatus.DNF
                self._log("DNF", f"{d.name} odpada (awaria/wypadek).")
                continue

            # pit jeśli trzeba (zużycie) lub wymóg FIA na sucho (2 mieszanki slick)
            force_compound_change = False
            if not self.raining:
                used_slicks = {c for c in d.used_compounds if c in (TireType.SOFT, TireType.MEDIUM, TireType.HARD)}
                planned = self._planned_pit_lap.get(d.name)
                if planned is not None and d.pit_stops == 0 and d.lap >= planned and len(used_slicks) < 2:
                    force_compound_change = True

            if self.pit_strategy.should_pit(self, d, force_compound_change=force_compound_change):
                next_compound = self.pit_strategy.pick_next_compound(self, d)
                pit_time = self.avg_pit_stop_s + self.rng.uniform(0.0, 2.0)
                d.total_time_s += pit_time
                d.pit_stops += 1
                d.tires = TireState(next_compound, wear_percent=100.0)
                d.used_compounds.add(next_compound)
                self._log(
                    "PIT",
                    f"{d.name} zjeżdża do pit: {next_compound.value} (+{pit_time:.1f}s).",
                )

            # okrążenie
            tires = d.ensure_tires()
            wear = self._wear_per_lap(d.skill, tires.tire_type)
            tires.apply_wear(wear)

            lap_time = self._lap_time_s(d, tires)
            if yellow_active:
                effects = self._driver_effects.get(d.name)
                lap_time *= (effects.pace_multiplier if effects else float(getattr(self.config, "yellow_pace_multiplier", 1.30)))
            d.last_lap_s = lap_time
            d.total_time_s += lap_time
            d.lap += 1

            if d.lap >= self.track_laps:
                d.status = DriverStatus.FINISHED
                self._log("FIN", f"{d.name} przekracza linię mety!")

        # żółta flaga: zakaz wyprzedzania → "dociśnij" czasy, aby zachować kolejność
        if yellow_active and order_before:
            name_to_driver = {d.name: d for d in self.drivers}
            ordered = [name_to_driver[n] for n in order_before if n in name_to_driver and name_to_driver[n].status == DriverStatus.RUNNING]
            min_gap = float(getattr(self.config, "yellow_min_gap_s", 0.20))
            prev_total: float | None = None
            for d in ordered:
                if prev_total is None:
                    prev_total = d.total_time_s
                    continue
                d.total_time_s = max(d.total_time_s, prev_total + min_gap)
                prev_total = d.total_time_s
            self._last_positions = [d.name for d in ordered]
        else:
            # wyprzedzenia
            now_positions = [d.name for d in self.sorted_running()]
            if self._last_positions:
                self._emit_overtakes(self._last_positions, now_positions)
            self._last_positions = now_positions

        # koniec: wszyscy aktywni dojechali
        still_running = any(d.status == DriverStatus.RUNNING for d in self.drivers)
        if not still_running:
            self._log("END", "Wyścig zakończony: wszyscy jadący ukończyli lub odpadli (DNF).")
            self.finished = True

        if not self.finished and yellow_triggered:
            min_laps = int(getattr(self.config, "yellow_flag_min_laps", 2))
            max_laps = int(getattr(self.config, "yellow_flag_max_laps", 6))
            if max_laps < min_laps:
                max_laps = min_laps
            new_duration = self.rng.randint(min_laps, max_laps)
            before_remaining = self._yellow_laps_remaining
            self._yellow_laps_remaining = max(self._yellow_laps_remaining, new_duration)
            self._set_flag(FlagState.YELLOW)

            # Logujemy tylko kiedy "ustawiamy" lub wydłużamy żółtą.
            if self._yellow_laps_remaining > before_remaining:
                reason = f" ({yellow_reason})" if yellow_reason else ""
                self._log("YEL", f"Żółta flaga na {self._yellow_laps_remaining} okr.{reason}.")

    def _emit_overtakes(self, before: list[str], after: list[str]) -> None:
        before_idx = {name: i for i, name in enumerate(before)}
        for i, name in enumerate(after):
            prev = before_idx.get(name)
            if prev is None:
                continue
            if i < prev:
                # awans
                gained = prev - i
                if gained >= 1:
                    noun = "pozycję" if gained == 1 else "pozycje"
                    self._log("OVT", f"Wyprzedzenie: {name} zyskuje {gained} {noun}.")
