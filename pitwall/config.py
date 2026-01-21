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
    collision_chance_per_lap: float = 0.002  # 0.2%
    incident_chance_per_lap: float = 0.008   # 0.8% (żółte flagi / drobny incydent)
    red_flag_chance_per_lap: float = 0.002   # 0.2% (globalnie)

    # DNF tuning (żeby nie było "za dużo" w stawce)
    dnf_chance_scale: float = 0.25
    collision_dnf_probability: float = 0.35

    # Ile realnych sekund „czeka” czerwona flaga (losowo w zakresie)
    red_flag_wait_min_s: float = 6.0
    red_flag_wait_max_s: float = 16.0

    # Ile MINUT dodaje czerwona flaga do czasu wyścigu (symulowany czas FIA)
    red_flag_duration_min_minutes: float = 15.0
    red_flag_duration_max_minutes: float = 30.0

    # Minimalny odstęp między czerwonymi flagami (w okrążeniach)
    red_flag_cooldown_laps: int = 8

    # Tempo opon (różnica między mieszankami slick na okrążeniu).
    # 0.007 = 0.7% czasu okrążenia na "krok" (SOFT->MEDIUM albo MEDIUM->HARD).
    tire_compound_delta_pct_per_step: float = 0.003

    # Żółta flaga
    yellow_flag_min_laps: int = 2
    yellow_flag_max_laps: int = 4
    yellow_pace_multiplier: float = 1.30
    yellow_min_gap_s: float = 0.20

    # Restart po czerwonej fladze ("zbijanie" stawki)
    restart_gap_s: float = 0.30


_CONFIG_SINGLETON = SimulationConfig()


def get_config() -> SimulationConfig:
    return _CONFIG_SINGLETON
