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
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

W trakcie działania:
- wybierasz tor (numer)
- dostajesz tabelę przedstartową (losowy grid + opony startowe + strategia)
- wciskasz Enter i startuje symulacja (tabela live + dwa panele logów)

---

## Struktura projektu — co jest gdzie

### Pliki w katalogu głównym

| Plik/katalog | Co zawiera / do czego służy |
|---|---|
| `main.py` | Punkt wejścia aplikacji (uruchamia `pitwall.app.run()`). |
| `requirements.txt` | Zależności Pythona (głównie `rich`). |
| `readme.MD` | Opis projektu, wzory modelu symulacji i instrukcja. |
| `UML.png` | Diagram UML dostarczony do projektu. |
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
| `pitwall/__init__.py` | Metadane pakietu. |

---

## Użyte wzorce projektowe (na przykładach z kodu)

### 1) Separacja warstw (Model–View–Controller w praktyce)

To nie jest „frameworkowy” MVC, ale jest czytelny podział odpowiedzialności:

- Model domeny: `Driver`, `Track`, `TireState` w `pitwall/models.py`
- Logika biznesowa/symulacja: `RaceSimulation` w `pitwall/race.py`
- Widok (renderowanie): `run_race_ui()` + `_build_table()` w `pitwall/ui.py`
- Kontroler/orchestrator: `run()` w `pitwall/app.py`

Efekt: UI nie miesza się z obliczaniem czasów okrążeń, a `RaceSimulation` nie musi znać szczegółów `rich`.

### 2) Strategy (dobór opon jako wymienna strategia)

Dobór opon jest wydzielony do metod kierowcy, dzięki czemu „strategia” jest lokalna i łatwa do zmiany:

```python
# pitwall/models.py
def pick_next_compound(self, raining: bool) -> TireType:
	...
```

Silnik wyścigu korzysta z tego bez wiedzy o szczegółach:

```python
# pitwall/race.py
next_compound = d.pick_next_compound(self.raining)
```

### 3) Dependency Injection (wstrzykiwanie zależności)

`RaceSimulation` dostaje zależności w konstruktorze, zamiast tworzyć je w środku:

```python
# pitwall/race.py
RaceSimulation(..., config=config, rng=rng)
```

To daje kontrolę nad:
- czasem symulacji (`SimulationConfig.race_real_seconds`)
- losowością (`random.Random()`), co ułatwia powtarzalność (np. przy debugowaniu).

### 4) Event queue / Observer-lite (emitowanie zdarzeń i konsumowanie w UI)

Symulacja publikuje zdarzenia jako listę `RaceEvent`, a UI je „subskrybuje” przez odczyt przyrostowy:

```python
# pitwall/race.py
self.events.append(RaceEvent(kind=..., message=...))

# pitwall/ui.py
log_index, new_events = sim.pop_new_events(log_index)
```

To pozwala mieć czytelne logi (oddzielnie „Wyprzedzenia” i „Zdarzenia”) bez sprzęgania UI z wnętrzem silnika.

### 5) State (stan kierowcy i stan opon)

`DriverStatus` i `TireState` modelują stan obiektu w czasie:
- kierowca przechodzi przez `RUNNING → FINISHED` albo `RUNNING → DNF`
- opony mają `wear_percent` oraz wynikającą z tego karę czasową (`TireState.penalty_s`)

To jest prosty, ale bardzo czytelny „state machine” dla potrzeb symulacji.