from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Iterable


class TireType(str, Enum):
    # Slicks
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    # Wet
    WET = "WET"


SLICK_COMPOUNDS: tuple[TireType, ...] = (TireType.SOFT, TireType.MEDIUM, TireType.HARD)


@dataclass(frozen=True)
class Team:
    name: str
    score: int  # 0-100


@dataclass(frozen=True)
class Track:
    name: str
    laps: int
    avg_pit_stop_s: float
    base_pace_s: float
    rain_chance_percent: int


@dataclass
class TireState:
    tire_type: TireType
    wear_percent: float = 100.0

    def apply_wear(self, amount: float) -> None:
        self.wear_percent = max(0.0, self.wear_percent - amount)

    @property
    def penalty_s(self) -> float:
        w = self.wear_percent
        if w > 30:
            return 0.0
        if 20 <= w <= 30:
            return 0.5
        if 10 <= w < 20:
            return 1.5
        return 3.0


class DriverStatus(str, Enum):
    RUNNING = "RUNNING"
    DNF = "DNF"
    FINISHED = "FINISHED"


@dataclass
class Driver:
    name: str
    team_name: str
    skill: int  # 0-100
    car_score: int  # 0-100

    status: DriverStatus = DriverStatus.RUNNING
    lap: int = 0

    total_time_s: float = 0.0
    last_lap_s: float = 0.0

    tires: TireState | None = None
    pit_stops: int = 0
    used_compounds: set[TireType] = field(default_factory=set)

    def is_active(self) -> bool:
        return self.status == DriverStatus.RUNNING

    def choose_start_tires(self, raining: bool, rng: random.Random) -> None:
        if raining:
            self.tires = TireState(TireType.WET)
            self.used_compounds = {TireType.WET}
            return

        # start: losowo (soft częściej)
        weights = {
            TireType.SOFT: 0.55,
            TireType.MEDIUM: 0.30,
            TireType.HARD: 0.15,
        }
        pick = rng.random()
        cumulative = 0.0
        chosen = TireType.SOFT
        for compound, w in weights.items():
            cumulative += w
            if pick <= cumulative:
                chosen = compound
                break

        self.tires = TireState(chosen)
        self.used_compounds = {chosen}

    def ensure_tires(self) -> TireState:
        if self.tires is None:
            self.tires = TireState(TireType.SOFT)
            self.used_compounds = {TireType.SOFT}
        return self.tires

    def needs_pit(self) -> bool:
        tires = self.ensure_tires()
        return tires.wear_percent < 20.0

    def pick_next_compound(self, raining: bool) -> TireType:
        if raining:
            return TireType.WET

        # FIA (sucho): w wyścigu trzeba mieć min. 2 różne mieszanki slick.
        used_slicks = {c for c in self.used_compounds if c in SLICK_COMPOUNDS}
        if len(used_slicks) < 2:
            for compound in SLICK_COMPOUNDS:
                if compound not in used_slicks:
                    return compound

        # po spełnieniu reguły: prosta heurystyka
        # jeśli mocno zużywa -> HARD, inaczej MEDIUM
        tires = self.ensure_tires()
        if tires.wear_percent < 10:
            return TireType.HARD
        return TireType.MEDIUM


def active_drivers(drivers: Iterable[Driver]) -> list[Driver]:
    return [d for d in drivers if d.status == DriverStatus.RUNNING]
