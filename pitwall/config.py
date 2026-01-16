from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationConfig:
    # Ile sekund w REALU ma trwać typowy wyścig (łatwo wydłużyć/skracać 1 zmienną).
    race_real_seconds: float = 60.0

    # Regulamin FIA: max 3h (tu jako limit symulowanego czasu wyścigu).
    race_sim_max_seconds: float = 3 * 60 * 60

    # UI
    ui_refresh_hz: float = 12.0
    max_log_lines: int = 14

    # Prawdopodobieństwa zdarzeń (na okrążenie, per kierowca / globalnie)
    collision_chance_per_lap: float = 0.004  # 0.4%
    incident_chance_per_lap: float = 0.010   # 1.0% (żółte flagi / drobny incydent)
    red_flag_chance_per_lap: float = 0.003   # 0.3% (globalnie)

    # Ile realnych sekund „czeka” czerwona flaga (losowo w zakresie)
    red_flag_wait_min_s: float = 6.0
    red_flag_wait_max_s: float = 16.0

    # Minimalny odstęp między czerwonymi flagami (w okrążeniach)
    red_flag_cooldown_laps: int = 8
