# VAULT STL repair

*(Polish version below / wersja polska niżej)*

Repairs the mesh errors of a whole **VAULT** STL library (USSA Design) in one go and writes a copy of the
library with the repaired files.

Many VAULT files have open or non-manifold edges and flipped faces, so Bambu Studio (and OrcaSlicer) ask
to repair them every time they are loaded. With a repaired copy of the library this stops.

Files without errors and all other files (PDF manuals, images) are copied unchanged, so the repaired
folder has exactly the structure of the original and can be used in its place – for example as the library
of the [VAULT configurator](https://github.com/rawel2/Vault-Konfigurator-wydania).

## Two methods

| | `--method windows` | `--method numpy` |
|---|---|---|
| How | the 3D model repair service built into Windows 10/11 (`Windows.Graphics.Printing3D`) – the same one Bambu Studio uses for "Repair model" | own repair written with numpy only (`numpy_repair.py`) |
| Systems | Windows 10/11 | Windows, macOS, Linux |
| Default on | Windows | macOS, Linux |
| Whole library (733 STL, 310 with errors) | about a day (22 h) | about 2 hours (1.9 h) |
| Files repaired to 0 errors | 310 of 310 | 308 of 310 – the S6 1F and 2F sustainer modules (the same wall stored up to 12 times) are copied unchanged |
| Largest XL modules (7 million triangles) | ~1.5 h each | 1–20 min each |

Times measured on a Core Ultra 7 258V laptop with 2 worker processes. The numpy method never writes a file worse
than the original: when the result still has errors or a different bounding box, the original is copied and the
file is reported as `still has errors`.

## Requirements

- Python 3.9 or newer – https://www.python.org/downloads/ (on Windows tick *Add python.exe to PATH*).
- `numpy` (and for the windows method the `winrt-*` packages) are installed automatically on the first run.

## Usage

Download `vault_stl_repair.py`, `numpy_repair.py` and the launcher for your system into one folder.

Windows:

```
vault_stl_repair.bat "D:\VAULT" "D:\VAULT_repaired"
vault_stl_repair.bat "D:\VAULT" "D:\VAULT_repaired" --method numpy
```

macOS / Linux (the script creates a private `.venv` with numpy when the system Python does not allow installing it):

```
chmod +x vault_stl_repair.sh
./vault_stl_repair.sh ~/VAULT ~/VAULT_repaired
```

The first folder is your VAULT library (the folder with `01. DRAWERS`, `02. SUSTAINERS`, …), the second is a
new folder for the repaired copy (it must not lie inside the first one). The same from a console:

```
python vault_stl_repair.py "D:\VAULT" "D:\VAULT_repaired"
```

Options:

| Option | Meaning |
|---|---|
| `--method M` | `auto` (default: windows on Windows, numpy elsewhere), `windows` or `numpy` |
| `--workers N` | parallel processes (default 2). The largest modules need a few GB of RAM each. |
| `--all` | repair also files without detected errors (by default they are copied unchanged) |
| `--only text` | only files whose path contains the text, e.g. `--only "S6"`; can be repeated |
| `--skip text` | leave out STL files whose path contains the text, e.g. `--skip XL`; can be repeated |

The largest files are processed first. Before each file with errors the script prints `repairing: <file>`, and after
each file how many are done, how many are left and an estimate of the remaining time (too high at the start, because
the big files go first). An interrupted run (Ctrl+C, reboot) can simply be started again: finished files are skipped
(`vault_stl_repair.json` in the target folder). (The XL modules are stored rotated by 42.8° and standing on their back,
with a 339.6 × 319.7 mm footprint, so they fit a 340 × 320 mm bed such as the Bambu Lab H2S.)

## Result

- The repaired library in the target folder.
- `vault_stl_repair.csv` in the target folder: for every STL file the status (`copied`, `repaired`,
  `still has errors`, `failed`), triangle counts and the numbers of open edges, non-manifold edges and flipped
  faces before and after. Open it in Excel.
- Repaired files have `VAULT STL repair (Windows Printing3D)` or `VAULT STL repair (numpy)` in the 80-byte STL header.

Repaired files are written with the centre of their bounding box at (0,0,0). The original files lie 1–28 m away
from the origin (they were exported from a large scene), where the STL format (32-bit floats) has a step of about
0.001 mm – the micro-triangles produced by the repair would collapse again at that distance. Shape and size are
unchanged; slicers centre imported files anyway.

## How much does the shape change?

Measured on the USSA library of 2026-10-21 (733 STL files) – every repaired file against its original:

| | numpy | Windows |
|---|---|---|
| Repaired files | 308 | 310 |
| Errors after repair (open + non-manifold + flipped) | 0 | 0 |
| Largest change of the bounding box | 0.0001 mm | 0.01 mm |
| Original → repaired, median / max | 0 / 0.94 mm | 0.004 / 3.98 mm |
| Original → repaired, files over 0.1 mm | 8 | 20 |
| Repaired → original, median / max | 0 / 0.83 mm | 0.004 / 0.86 mm |
| Repaired → original, files over 0.1 mm | 3 | 1 |
| Volume change over 0.1 % | 4 files | 4 files |

The two directions mean different things:

- **original → repaired** – how far the original surface is from the repaired one. Large values here mean that the
  repair *removed* something: in all these files thin flaps of the original with no volume (zero-thickness walls,
  doubled strips) – the volume of these files did not change.
- **repaired → original** – how far the new surface is from the original. Large values mean that the repair *added*
  a surface away from the original: a patch over a real hole (S5 Roof: a 52 × 1.9 mm gap in the original lid).

Files with a deviation over 0.1 mm in either method (maximum distance in mm):

| File | Type | numpy orig→rep | numpy rep→orig | Windows orig→rep | Windows rep→orig |
|---|---|---|---|---|---|
| L5 Module 1F | drawer module | 0.51 | 0.07 | 3.88 | 0.08 |
| L5 Module 2F | drawer module | 0.48 | 0.03 | 3.87 | 0.01 |
| L5 Module 4F | drawer module | 0.43 | 0.00 | 3.98 | 0.01 |
| L7 Module 4F | drawer module | 0.94 | 0.34 | 3.95 | 0.01 |
| L7² Module 4F | drawer module | 0.26 | 0.00 | 0.01 | 0.01 |
| S1F (Turn On Supports) | drawer facade | 0.15 | 0.15 | 0.00 | 0.00 |
| S4 Box 1F | drawer box | 0.00 | 0.00 | 0.18 | 0.00 |
| XL3 Grid Roof | drawer roof | 0.00 | 0.00 | 1.88 | 0.00 |
| S5 Roof | sustainer lid | 0.00 | 0.83 | 0.00 | 0.86 |
| S6 1F Module | sustainer module | not repaired | – | 0.45 | 0.00 |
| S6 2F Module | sustainer module | not repaired | – | 0.56 | 0.00 |
| S6 4F Module | sustainer module | 0.01 | 0.00 | 0.57 | 0.00 |
| S7 1F Module | sustainer module | 0.00 | 0.00 | 0.58 | 0.00 |
| S7 2F Module | sustainer module | 0.00 | 0.00 | 0.54 | 0.00 |
| M3 4F Module | sustainer module | 0.17 | 0.00 | 0.00 | 0.00 |
| M6 1F Module | sustainer module | 0.00 | 0.00 | 0.11 | 0.00 |
| L3 1F Dividers Module | sustainer module | 0.12 | 0.02 | 0.62 | 0.00 |
| L3 2F Dividers Module | sustainer module | 0.01 | 0.00 | 0.60 | 0.00 |
| L3 4F Dividers Module | sustainer module | 0.00 | 0.00 | 0.53 | 0.00 |
| L6 2F Sealed Module | sustainer module | 0.00 | 0.00 | 0.42 | 0.01 |
| XL4 1F Dividers Module | sustainer module | 0.00 | 0.00 | 0.23 | 0.01 |
| XL6 1F Dividers Module | sustainer module | 0.00 | 0.00 | 0.24 | 0.01 |
| XL7 1F Dividers Module | sustainer module | 0.00 | 0.00 | 0.21 | 0.01 |
| L Pull-out Handle Lock | modification | 0.04 | 0.00 | 0.19 | 0.00 |

The full lists for every repaired file are in [`results/deviations_numpy.csv`](results/deviations_numpy.csv) and
[`results/deviations_windows.csv`](results/deviations_windows.csv) (errors before/after, volume, bounding box,
deviation in both directions, share of the repaired surface further than 0.1 mm from the original).

**How it was measured:** the one-sided Hausdorff distance in both directions with
[pymeshlab](https://pymeshlab.readthedocs.io/) (`get_hausdorff_distance`, 200 000 sample points on the faces of the
measured mesh), with both meshes centred on their bounding box (the repaired file is written at the origin; the
bounding box itself does not change, see above). The maxima come from sampling, so they vary slightly between runs
(up to about 0.1 mm for the largest values).

## How it works

Each STL file is first checked with numpy (edges counted after merging vertices at exactly equal coordinates,
like admesh in slicers).

**windows:** a file with errors is written as a 3MF package in memory, loaded with `Printing3D3MFPackage`, repaired
with `Printing3DModel.RepairAsync()` and saved back as a binary STL with recomputed normals. That is the route
PrusaSlicer and Bambu Studio take in `FixModelByWin10.cpp`; a mesh built directly in memory is rejected by the
service, so the 3MF step is required. The service output is closed when read by vertex indices, but in the biggest
files it leaves a few dozen pairs of vertices at exactly the same position under different indices; STL has no
indices, so the tool moves such vertices apart by at most 0.002 mm towards their neighbours before writing.

**numpy:** the defects of the VAULT files are mostly pairs of duplicated faces with opposite orientation
(zero-thickness walls), flat zero-height triangles, slits with T-junctions, a few real holes, flaps lying on or
sticking out of another surface and inside-out shells. `numpy_repair.py` removes the opposite face pairs, stitches
the slits, closes the holes, removes the flaps, splits the remaining non-manifold edges into separate surfaces and
makes the orientation of every shell consistent; small knots that are left are cut out and patched again. Files with
more than 20 000 non-manifold edges after cleaning (the S6 1F/2F sustainer modules, about 65 000) are left unchanged.

## About

Part of the unofficial VAULT configurator: https://github.com/rawel2/Vault-Konfigurator-wydania
Authors: rawel2 and Claude (Anthropic). MIT licence (see LICENSE).
VAULT, its design and STL files © USSA Design – they are not part of this project.

---

# Naprawa siatek STL VAULT (PL)

Naprawia za jednym razem błędy siatek całej biblioteki STL systemu **VAULT** (USSA Design) i zapisuje kopię
biblioteki z naprawionymi plikami.

Wiele plików VAULT ma otwarte lub nierozmaitościowe krawędzie i odwrócone ściany, dlatego Bambu Studio
(i OrcaSlicer) przy każdym wczytaniu proponuje naprawę. Z naprawioną kopią biblioteki to się kończy.

Pliki bez błędów i wszystkie inne pliki (instrukcje PDF, obrazki) są kopiowane bez zmian, więc naprawiony folder
ma dokładnie strukturę oryginału i może go zastąpić – np. jako biblioteka
[konfiguratora VAULT](https://github.com/rawel2/Vault-Konfigurator-wydania).

## Dwie metody

- **`--method windows`** (domyślna w Windows) – usługa naprawy modeli 3D wbudowana w Windows 10/11
  (`Windows.Graphics.Printing3D`), ta sama co „Napraw model” w Bambu Studio. Naprawia wszystkie 310 plików
  z błędami, ale cała biblioteka trwa ok. doby (moduły XL po ok. 1,5 h).
- **`--method numpy`** (domyślna w macOS i Linuksie) – własna naprawa samym numpy (`numpy_repair.py`), każdy system.
  Cała biblioteka ok. 2 godzin. Naprawia 308 z 310 plików; skrzynki S6 1F i 2F Module (ta sama ściana zapisana do
  12 razy) są kopiowane bez zmian. Metoda nigdy nie zapisuje pliku gorszego od oryginału.

## Wymagania

- Python 3.9 lub nowszy – https://www.python.org/downloads/ (w Windows zaznacz *Add python.exe to PATH*).
- `numpy` (a dla metody windows pakiety `winrt-*`) instalują się same przy pierwszym uruchomieniu.

## Użycie

Pobierz `vault_stl_repair.py`, `numpy_repair.py` i skrypt startowy dla swojego systemu do jednego folderu.

Windows:

```
vault_stl_repair.bat "D:\VAULT" "D:\VAULT_naprawione"
vault_stl_repair.bat "D:\VAULT" "D:\VAULT_naprawione" --method numpy
```

macOS / Linux (skrypt sam zakłada prywatne `.venv` z numpy, gdy systemowy Python nie pozwala go zainstalować):

```
chmod +x vault_stl_repair.sh
./vault_stl_repair.sh ~/VAULT ~/VAULT_naprawione
```

Pierwszy folder to biblioteka VAULT (folder z `01. DRAWERS`, `02. SUSTAINERS`, …), drugi – nowy folder na
naprawioną kopię (nie może leżeć wewnątrz pierwszego).

Opcje: `--method` (`auto`, `windows`, `numpy`), `--workers N` (liczba równoległych procesów, domyślnie 2; największe
moduły zajmują po kilka GB RAM), `--all` (naprawiaj także pliki bez wykrytych błędów), `--only tekst` (tylko pliki,
których ścieżka zawiera tekst), `--skip tekst` (pomiń pliki STL z tekstem w ścieżce, np. `--skip XL`).

Największe pliki idą pierwsze. Przed każdym plikiem z błędami skrypt wypisuje `repairing: <plik>`, a po każdym
pliku – ile zrobił, ile zostało i szacowany pozostały czas. Przerwane uruchomienie (Ctrl+C, restart) można po prostu
uruchomić ponownie: gotowe pliki są pomijane (`vault_stl_repair.json` w folderze docelowym).

## Wynik

- Naprawiona biblioteka w folderze docelowym.
- `vault_stl_repair.csv`: dla każdego pliku status (`copied`, `repaired`, `still has errors`, `failed`), liczba
  trójkątów oraz otwarte i nierozmaitościowe krawędzie i odwrócone ściany przed i po naprawie.
- Naprawione pliki mają w nagłówku STL `VAULT STL repair (Windows Printing3D)` albo `VAULT STL repair (numpy)`.
- Naprawione pliki są zapisywane ze środkiem bryły w punkcie (0,0,0) – oryginały leżą 1–28 m od początku układu,
  gdzie format STL ma krok ok. 0,001 mm. Kształt i wymiary bez zmian; slicery i tak centrują wczytane pliki.

## Jak bardzo zmienia się kształt?

Pomiar na bibliotece USSA z 2026-10-21 (733 pliki STL), każdy naprawiony plik wobec oryginału – tabele i opis
w części angielskiej wyżej. W skrócie: po naprawie 0 błędów w obu metodach, wymiary bez zmian (numpy ≤ 0,0001 mm,
Windows ≤ 0,01 mm), typowa odchyłka 0 mm (numpy) / 0,004 mm (Windows). Większe odchyłki „oryginał → naprawiony”
(numpy w 8 plikach do 0,94 mm, Windows w 20 plikach do 3,98 mm) to usunięte cienkie płaty oryginału bez objętości;
„naprawiony → oryginał” – łata na prawdziwej dziurze w wieku S5 Roof (0,83 / 0,86 mm). Pełne listy:
`results/deviations_numpy.csv` i `results/deviations_windows.csv`. Pomiar: jednostronna odległość Hausdorffa w obie
strony w pymeshlab (`get_hausdorff_distance`, 200 000 punktów na ścianach), obie siatki wyśrodkowane na bryle.

## Autorzy i prawa

Część nieoficjalnego konfiguratora VAULT: https://github.com/rawel2/Vault-Konfigurator-wydania
Autorzy: rawel2 i Claude (Anthropic). Licencja MIT (plik LICENSE).
VAULT, jego projekt i pliki STL © USSA Design – nie są częścią tego projektu.
