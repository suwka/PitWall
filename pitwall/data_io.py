from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from pitwall.models import Driver, Team, Track


@dataclass(frozen=True)
class DataBundle:
    drivers: list[Driver]
    teams: dict[str, Team]
    tracks: list[Track]


def _parse_lap_pace_to_seconds(text: str) -> float:
    # format: M:SS or M:SS.ms
    value = text.strip()
    if ":" not in value:
        return float(value)
    minutes_str, seconds_str = value.split(":", 1)
    minutes = int(minutes_str)
    seconds = float(seconds_str)
    return minutes * 60 + seconds


def _normalize_team_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _resolve_team_score(team_name: str, teams: dict[str, Team]) -> int:
    # Teams w CSV nie zawsze mają identyczne nazwy — mapowanie aliasów.
    aliases = {
        "red bull": "red bull racing",
        "racing bulls": "red bull racing",
        "haas": "haas f1 team",
    }
    key = _normalize_team_name(team_name)
    key = aliases.get(key, key)

    # szybka próba dopasowania po znormalizowanej nazwie
    normalized_map = {_normalize_team_name(t.name): t for t in teams.values()}
    team = normalized_map.get(key)
    if team is None:
        # fallback: średniak
        return 70
    return int(team.score)


def load_data(data_dir: Path) -> DataBundle:
    drivers_path = data_dir / "drivers.csv"
    teams_path = data_dir / "teams.csv"
    tracks_path = data_dir / "tracks.csv"

    teams: dict[str, Team] = {}
    with teams_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["team"].strip()
            teams[name] = Team(name=name, score=int(float(row["score"])) )

    tracks: list[Track] = []
    with tracks_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tracks.append(
                Track(
                    name=row["tor"].strip(),
                    laps=int(row["okrazenia"]),
                    avg_pit_stop_s=float(row["avg_pit_stop_s"]),
                    base_pace_s=_parse_lap_pace_to_seconds(row["avg_lap_race_pace"]),
                    rain_chance_percent=int(float(row["szansa_deszczu_proc"])),
                )
            )

    drivers: list[Driver] = []
    with drivers_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            team_name = row["team"].strip()
            drivers.append(
                Driver(
                    name=row["nazwa"].strip(),
                    team_name=team_name,
                    skill=int(float(row["rating"])),
                    car_score=_resolve_team_score(team_name, teams),
                )
            )

    return DataBundle(drivers=drivers, teams=teams, tracks=tracks)
