# VAULT STL repair

*(Polish version below / wersja polska niżej)*

Repairs the mesh errors of a whole **VAULT** STL library (USSA Design) in one go and writes a copy of the
library with the repaired files. It uses the **same repair service as Bambu Studio's "Repair model"**: the
3D model repair API built into Windows 10/11 (`Windows.Graphics.Printing3D`), so the result is what you get
by clicking "Repair" in the slicer – just for all files at once and only once.

Many VAULT files have open or non-manifold edges and flipped faces, so Bambu Studio (and OrcaSlicer) ask
to repair them every time they are loaded. With a repaired copy of the library this stops.

Files without errors and all other files (PDF manuals, images) are copied unchanged, so the repaired
folder has exactly the structure of the original and can be used in its place – for example as the library
of the [VAULT configurator](https://github.com/rawel2/Vault-Konfigurator-wydania).

## Requirements

- Windows 10 or 11 (the repair service is part of Windows; no 3D Builder needed).
- Python 3.9 or newer – https://www.python.org/downloads/ (tick *Add python.exe to PATH*).
- Packages `numpy` and `winrt-*` are installed automatically on the first run.

## Usage

Download `vault_stl_repair.py` and `vault_stl_repair.bat` into one folder, then:

```
vault_stl_repair.bat "D:\VAULT" "D:\VAULT_repaired"
```

The first folder is your VAULT library (the folder with `01. DRAWERS`, `02. SUSTAINERS`, …), the second is a
new folder for the repaired copy (it must not lie inside the first one). The same from a console:

```
python vault_stl_repair.py "D:\VAULT" "D:\VAULT_repaired"
```

Options:

| Option | Meaning |
|---|---|
| `--workers N` | parallel processes (default 2). The largest modules need a few GB of RAM each. |
| `--all` | repair also files without detected errors (by default they are copied unchanged) |
| `--only text` | only files whose path contains the text, e.g. `--only "S6"`; can be repeated |
| `--skip text` | leave out STL files whose path contains the text, e.g. `--skip XL`; can be repeated |

The XL modules (`XL3`–`XL7` and `XL3²`–`XL7²`, up to 7 million triangles each) take about 1.5 hours each – `--skip XL`
saves several hours if you do not print XL. (They are stored rotated by 42.8° and standing on their back, with a
339.6 × 319.7 mm footprint, so they fit a 340 × 320 mm bed such as the Bambu Lab H2S.)

The whole library (733 STL files, about 24 GB) takes **a few hours** – the service is slow on large modules
(a 1.4-million-triangle module takes about 4–5 minutes). The largest files are processed first, and after
each file the script prints how many are done, how many are left and an estimate of the remaining time.
An interrupted run (Ctrl+C, reboot) can simply be started again: finished files are skipped
(`vault_stl_repair.json` in the target folder).

## Result

- The repaired library in the target folder.
- `vault_stl_repair.csv` in the target folder: for every STL file the status (`copied`, `repaired`,
  `still has errors`, `failed`), triangle counts and the numbers of open edges, non-manifold edges and flipped
  faces before and after. Open it in Excel.
- Repaired files have `VAULT STL repair (Windows Printing3D)` in the 80-byte STL header.

The repair keeps the geometry: in the tests the volume and the bounding box of repaired parts were identical to
the originals (e.g. S6 1F module: 104 213 non-manifold edges and 207 990 flipped faces → 0, volume 406.6 → 406.7 cm³;
the triangle count drops because duplicated faces are removed).

Repaired files are written with the centre of their bounding box at (0,0,0). The original files lie 1–28 m away
from the origin (they were exported from a large scene), where the STL format (32-bit floats) has a step of about
0.001 mm – the micro-triangles produced by the repair would collapse again at that distance (the XL5² module came out
with 51 new bad edges before this change). Shape and size are unchanged; slicers centre imported files anyway.

The service output is closed when read by vertex indices, but in the biggest files (the XL modules) it leaves a few
dozen pairs of vertices at exactly the same position under different indices. STL has no indices, so those vertices
would merge on export and the file would still show non-manifold edges in the slicer (the XL modules used to end
as `still has errors`). The tool therefore moves such vertices apart by at most 0.002 mm towards their neighbours
before writing (XL5² module: 48 pairs → 0 errors, volume 908.6 → 908.6 cm³).

## How it works

Each STL file is first checked with numpy (edges counted after merging vertices at exactly equal coordinates,
like admesh in slicers). A file with errors is written as a 3MF package in memory, loaded with
`Printing3D3MFPackage`, repaired with `Printing3DModel.RepairAsync()` and saved back as a binary STL with
recomputed normals. That is the route PrusaSlicer and Bambu Studio take in `FixModelByWin10.cpp`; a mesh built
directly in memory is rejected by the service, so the 3MF step is required.

## About

Part of the unofficial VAULT configurator: https://github.com/rawel2/Vault-Konfigurator-wydania
Authors: rawel2 and Claude (Anthropic). MIT licence (see LICENSE).
VAULT, its design and STL files © USSA Design – they are not part of this project.

---

# Naprawa siatek STL VAULT (PL)

Naprawia za jednym razem błędy siatek całej biblioteki STL systemu **VAULT** (USSA Design) i zapisuje kopię
biblioteki z naprawionymi plikami. Używa **tej samej usługi, co „Napraw model” w Bambu Studio** – wbudowanego
w Windows 10/11 API naprawy modeli 3D (`Windows.Graphics.Printing3D`), więc wynik jest taki, jak po kliknięciu
„Napraw” w slicerze, tylko dla wszystkich plików naraz i tylko raz.

Wiele plików VAULT ma otwarte lub nierozmaitościowe krawędzie i odwrócone ściany, dlatego Bambu Studio
(i OrcaSlicer) przy każdym wczytaniu proponuje naprawę. Z naprawioną kopią biblioteki to się kończy.

Pliki bez błędów i wszystkie inne pliki (instrukcje PDF, obrazki) są kopiowane bez zmian, więc naprawiony folder
ma dokładnie strukturę oryginału i może go zastąpić – np. jako biblioteka
[konfiguratora VAULT](https://github.com/rawel2/Vault-Konfigurator-wydania).

## Wymagania

- Windows 10 lub 11 (usługa naprawy jest częścią systemu; 3D Builder nie jest potrzebny).
- Python 3.9 lub nowszy – https://www.python.org/downloads/ (zaznacz *Add python.exe to PATH*).
- Pakiety `numpy` i `winrt-*` instalują się same przy pierwszym uruchomieniu.

## Użycie

Pobierz `vault_stl_repair.py` i `vault_stl_repair.bat` do jednego folderu, potem:

```
vault_stl_repair.bat "D:\VAULT" "D:\VAULT_naprawione"
```

Pierwszy folder to biblioteka VAULT (folder z `01. DRAWERS`, `02. SUSTAINERS`, …), drugi – nowy folder na
naprawioną kopię (nie może leżeć wewnątrz pierwszego). To samo z konsoli:

```
python vault_stl_repair.py "D:\VAULT" "D:\VAULT_naprawione"
```

Opcje: `--workers N` (liczba równoległych procesów, domyślnie 2; największe moduły zajmują po kilka GB RAM),
`--all` (naprawiaj także pliki bez wykrytych błędów), `--only tekst` (tylko pliki, których ścieżka zawiera tekst),
`--skip tekst` (pomiń pliki STL z tekstem w ścieżce). Moduły XL (`XL3`–`XL7`, `XL3²`–`XL7²`, do 7 mln trójkątów) trwają
po około 1,5 godziny – `--skip XL` oszczędza kilka godzin, jeśli nie drukujesz XL. (W plikach leżą obrócone o 42,8°
i postawione na tylnej ścianie, obrys 339,6 × 319,7 mm, więc mieszczą się na stole 340 × 320 mm, np. Bambu Lab H2S.)

Cała biblioteka (733 pliki STL, ok. 24 GB) trwa **kilka godzin** – usługa jest wolna na dużych modułach
(moduł z 1,4 mln trójkątów ok. 4–5 minut). Największe pliki idą pierwsze, a po każdym pliku skrypt wypisuje,
ile zrobił, ile zostało i szacowany pozostały czas. Przerwane uruchomienie (Ctrl+C, restart) można po prostu
uruchomić ponownie: gotowe pliki są pomijane (`vault_stl_repair.json` w folderze docelowym).

## Wynik

- Naprawiona biblioteka w folderze docelowym.
- `vault_stl_repair.csv` w folderze docelowym: dla każdego pliku status (`copied`, `repaired`, `still has errors`,
  `failed`), liczba trójkątów oraz otwarte i nierozmaitościowe krawędzie i odwrócone ściany przed i po naprawie.
- Naprawione pliki mają w nagłówku STL tekst `VAULT STL repair (Windows Printing3D)`.

Naprawa zachowuje geometrię: w testach objętość i wymiary naprawionych części były identyczne z oryginałem
(np. moduł S6 1F: 104 213 krawędzi nierozmaitościowych i 207 990 odwróconych ścian → 0, objętość 406,6 → 406,7 cm³;
liczba trójkątów spada, bo usuwane są zdublowane ściany).

Naprawione pliki są zapisywane ze środkiem bryły otaczającej w punkcie (0,0,0). Oryginały leżą 1–28 m od początku
układu (eksport z dużej sceny), gdzie format STL (liczby 32-bitowe) ma krok ok. 0,001 mm – mikrotrójkąty z naprawy
zlewałyby się tam ponownie (moduł XL5² przed tą zmianą wychodził z 51 nowymi złymi krawędziami). Kształt i wymiary
bez zmian; slicery i tak centrują wczytane pliki.

Wynik usługi jest zamknięty, gdy czytać go po indeksach wierzchołków, ale w największych plikach (moduły XL) zostawia
kilkadziesiąt par wierzchołków o identycznym położeniu pod różnymi indeksami. STL nie ma indeksów, więc przy zapisie
zlałyby się w jeden i plik dalej pokazywałby w slicerze krawędzie nierozmaitościowe (moduły XL kończyły jako
`still has errors`). Narzędzie odsuwa więc takie wierzchołki o najwyżej 0,002 mm w stronę sąsiadów przed zapisem
(moduł XL5²: 48 par → 0 błędów, objętość 908,6 → 908,6 cm³).

## Autorzy i prawa

Część nieoficjalnego konfiguratora VAULT: https://github.com/rawel2/Vault-Konfigurator-wydania
Autorzy: rawel2 i Claude (Anthropic). Licencja MIT (plik LICENSE).
VAULT, jego projekt i pliki STL © USSA Design – nie są częścią tego projektu.
