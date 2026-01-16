# F1 Simulation — uproszczony model
Projekt zaliczeniowy realizujący symulację wyścigu Formuły 1 w oparciu o paradygmat programowania obiektowego (OOP). System modeluje złożony, nieliniowy problem rywalizacji sportowej, uwzględniając czynniki losowe, parametry techniczne bolidów oraz umiejętności kierowców.

Projekt został zaimplementowany w języku **Python**.

Symulacja wyścigu F1 z tabelą aktualizowaną co okrążenie. Prosty model, ale z nieliniowością (pit stopy, DNF, degradacja opon).

---

## Dane wejściowe

| Plik | Kolumny |
|------|---------|
| `drivers.csv` | `nazwa`, `team`, `rating` (skill 0–100) |
| `teams.csv` | `team`, `score` (performance auta 0–100) |
| `tracks.csv` | `tor`, `okrazenia`, `avg_pit_stop_s`, `avg_lap_race_pace`, `szansa_deszczu_proc` |

---

## Model symulacji

### 1. Tempo okrążenia

Czas okrążenia kierowcy zależy od **skillu** (70%) i **auta** (30%) + losowy rozrzut.

```
lap_time = base_pace - (skill * 0.007) - (car_score * 0.003) + random(-0.3, +0.3) + tire_penalty
```

- `base_pace` — z `tracks.csv` (`avg_lap_race_pace`)
- Lepszy kierowca/auto = niższy czas
- `tire_penalty` — kara za zużyte opony (patrz niżej)

---

### 2. Opony i pit stopy

Każdy kierowca startuje ze 100% stanu opon.

**Degradacja na okrążenie:**

```
wear_per_lap = 2.0 - (skill * 0.01)
```

- Mistrz (skill 100): traci 1% / okrążenie
- Słaby (skill 50): traci 1.5% / okrążenie

**Kara za zużycie:**

| Stan opon | Kara do czasu |
|-----------|---------------|
| > 30% | +0s |
| 20–30% | +0.5s |
| 10–20% | +1.5s |
| < 10% | +3s (krytyczne!) |

**Pit stop:** gdy opony < 20%, kierowca musi zjechać. Czas pit stopu = `avg_pit_stop_s` z toru + random(0, 2s).

---

### 3. DNF (wypadki / awarie)

Co okrążenie każdy kierowca ma małą szansę na DNF:

```
dnf_chance = 0.2% + (100 - skill) * 0.01%
```

- Mistrz: ~0.2% / okrążenie
- Słaby: ~0.7% / okrążenie

Przy 50 okrążeniach → realnie 1–3 DNF na wyścig.

---

### 4. Klasyfikacja

Po każdym okrążeniu sortujesz kierowców po **łącznym czasie**. Kto ma DNF, odpada z tabeli.

---

## Podsumowanie: co wpływa na wyścig

| Czynnik | Wpływ |
|---------|-------|
| Skill kierowcy | Tempo, zarządzanie oponami, mniej DNF |
| Performance auta | Tempo (mniejszy wpływ niż skill) |
| Pit stopy | Skoki w pozycjach (nieliniowość!) |
| DNF | Losowe odpady |

---

## Uruchomienie (Windows)

W katalogu projektu:

```powershell
python main.py
```

W trakcie działania:
- wybierasz tor (numer)
- wciskasz Enter i startuje symulacja (tabela live + dwa panele logów)
- dostajesz tabelę (losowy grid + opony startowe + strategia)

---

## Struktura projektu — co jest gdzie

### Pliki w katalogu głównym

| Plik/katalog | Co zawiera / do czego służy |
|---|---|
| `main.py` | Punkt wejścia aplikacji (uruchamia `pitwall.app.run()`). |
| `requirements.txt` | Zależności Pythona (głównie `rich`). |
| `data/` | Dane wejściowe do symulacji (CSV). |
| `pitwall/` | Właściwy kod aplikacji (modele, logika wyścigu, UI). |

### `data/`

| Plik | Co zawiera |
|---|---|
| `data/drivers.csv` | Lista kierowców: `nazwa`, `team`, `rating`. |
| `data/teams.csv` | Osiągi zespołów/aut: `team`, `score`. |
| `data/tracks.csv` | Parametry torów: `tor`, `okrazenia`, `avg_pit_stop_s`, `avg_lap_race_pace`, `szansa_deszczu_proc`. |

### `pitwall/`

| Plik | Co zawiera |
|---|---|
| `pitwall/config.py` | Konfiguracja symulacji w `SimulationConfig` (m.in. `race_real_seconds` jako przelicznik czasu, prawdopodobieństwa zdarzeń, limity FIA). |
| `pitwall/models.py` | Modele domenowe: `Driver`, `Team`, `Track`, `TireState`, enumy `TireType` i `DriverStatus`, logika doboru opon (`choose_start_tires`, `pick_next_compound`). |
| `pitwall/data_io.py` | Warstwa wczytywania danych: `load_data()` czyta CSV i zwraca `DataBundle`; zawiera parser czasu okrążenia i dopasowanie teamów. |
| `pitwall/race.py` | Silnik symulacji: `RaceSimulation` + `RaceEvent`. Metoda `step_lap()` robi pełną aktualizację per okrążenie (czasy, zużycie, pit, DNF, zdarzenia, wyprzedzenia, czerwone flagi). |
| `pitwall/ui.py` | UI w `rich`: budowanie tabeli, layout (tabela + dwa panele logów), odliczanie czerwonej flagi, prezentacja wyników. |
| `pitwall/app.py` | Orkiestracja: wybór toru, losowanie pogody i ustawienia kierowców, przygotowanie opon/strategii (`sim.prepare()`), start UI. |


---
