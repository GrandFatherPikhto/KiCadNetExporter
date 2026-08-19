# KiCad Net Exporter

Simplifies and flattens KiCad netlists (including hierarchical projects) into a
form readable by both humans and AI, audits netclass classification of nets,
watches project files in the background, and places reports next to the project.

> **[README на русском](README_ru.md)**

## Architecture

```
netexp/
  core/    — data models and protocols (Component, Net, PinConnection, NetlistDocument...).
             Knows nothing about YAML/sexpdata/watchdog. The fields intentionally mirror
             NetlistDocument/Component/Net/PinConnection from the sibling C# project
             NetFileConverter.Core — the JSON produced by one tool can in principle be
             read by the other.
  infra/   — implementations: .net parser (sexpdata + custom semantics), .kicad_pro parser (json),
             netclass classifier, report generators.
  app/     — config, logging, watcher, tray, entry point.
```

If a KiCad IPC API for the schematic editor appears (or gets fixed) tomorrow,
only `infra/parsers` changes; the rest of the code works through the protocols
in `core/interfaces.py` and stays untouched.

## Installation

```
pip install -r requirements.txt
```

(on Windows, use `pythonw.exe` instead of `python.exe` for console-less autostart)

## Configuration

A single YAML file covers all projects. See `config.example.yaml` for detailed
comments on every section. `config.yaml` in the same folder is already set up
for mishin-coil-gen-v1 — adjust the paths if the project moved.

In short:

- `projects` — list of (.kicad_pro + .net) pairs with an output folder. Multiple allowed.
- `output.formats` — which formats to write: `txt` (for humans), `json` (for scripts/AI),
  `md` (same as txt, but with markdown formatting).
- `output.raw_txt_copy` — if true, an exact copy of `*.net` is placed next to the reports
  under the name `*.txt` (preserving the modification time) — for tools like DeepSeek
  that don't understand the `.net` extension.
- `output.diff` — write `<project>_diff.*` with changes since the last run
  (the other reports themselves are not diffed — they are simply overwritten in full).
- `classification.power_patterns` / `suspicious_patterns` — regex lists for
  detecting power nets and "suspicious" Default-class nets. Edit them here,
  no code changes needed.
- `watch` — debounce delays.
- `logging` — level/file/rotation. It's better not to put the log file in the same folder
  as the watched `.net`/`.kicad_pro` (not critical for correctness, but on some
  network/synced drives extra log events can slow down the watcher).
- `tray.enabled` — system tray icon.

## Running

One-off run (no watcher, no tray), handy for checking the config:

```bash
python -m netexp.app.main config.yaml --once
```

Background mode (watcher + tray), for development — with a console:

```bash
python -m netexp.app.main config.yaml
```

For a real background run on Windows — without a console:

```bash
pythonw -m netexp.app.main config.yaml
```

From the tray: open the output folder(s), open the log, pause, exit.

Autostart at Windows login — the simplest way: a shortcut to
`pythonw.exe -m netexp.app.main C:\path\to\config.yaml` in the
`shell:startup` folder.

## What gets generated in output_dir

For each project, for each enabled format (`txt`/`json`/`md`):

- `<name>_net.*` — simplified netlist as a tree by hierarchy sheets; the full
  net name and its netclass are always shown.
- `<name>_bom.*` — bill of materials; missing footprints are highlighted separately.
- `<name>_unconnected.*` — unconnected/no-connect nets (previously just dropped).
- `<name>_power.*` — power nets (per `power_patterns` from the config).
- `<name>_audit.*` — net class report: what went where, overlaps, what is left
  in Default and what of that is suspicious, plus each class's routing rules
  (track_width/clearance/via/diff-pair from Board Setup) — so you don't have to
  check in KiCad by eye whether PA_Signal really is 2.0 mm.
- `<name>_patterns.*` — dump of the netclass patterns from `.kicad_pro` with
  warnings (extra backslash, reference to an undeclared class).
- `<name>_diff.*` — what changed since the previous run.
- `<name>.txt` — exact copy of `.net` (only when `raw_txt_copy: true`).
- `.snapshot_<name>.json` — internal file for diff, don't touch it by hand.

## Tests

Unit tests (`pytest`) live in `tests/` and cover models, parsers
(`.net`/`.kicad_pro`), classification, all report generators, and the app layer
(config, pipeline, watcher, logging). Synthetic test data is generated in `tests/data.py`.

```bash
pip install pytest
python -m pytest
```

## Sample / test on your own data

`test_sample/` contains a synthetic hierarchical project (demonstrating sheets,
unconnected and power nets, a component without a footprint, a "bad" escape in a
pattern, and a reference to an undeclared class) plus an already-run `out/` with
examples of every report. Use `test_sample/config.yaml` as a reference.

## Verified on a real project

Ran on mishin-coil-gen-v1 (KiCad 10.0.4, hierarchical, 322 components,
221 nets, 17 netclasses) — parsed and classified fully, 0 nets left in Default.
By the way, the `.net` parser was originally based on `kinparse`
(a specialized pyparsing grammar) — it failed on the same project: the `design`
section in KiCad 10 contains a `(sheet ...)`/`(title_block ...)` entry per
hierarchy sheet, and the grammar didn't expect it. Replaced with `sexpdata`
(a generic S-expr tokenizer) plus a custom semantic layer on top — it doesn't
try to understand the format entirely, just extracts the needed fields and
silently skips everything unfamiliar. Switching libraries didn't touch anything
except `net_parser.py` — exactly why the interface in `core/interfaces.py` exists.

## Known limitations

- Netclass pattern matching runs against the **full** hierarchical net name
  (as in the old `netclass_audit.py`). If a pattern is written with `^...$`
  for a flat project (e.g. `^\+5V$`), it won't match `/Power/SubSheetA/+5V`
  on a nested sheet — account for the path in the pattern or drop the anchors.
  On the real project this is already handled: patterns there look like
  `^(?:.*/)?+5V.*`.
- `raw_txt_copy` preserves modification/access time (`shutil.copystat`), but not
  the file creation time on NTFS (Windows Explorer shows it separately) —
  that would require `pywin32`, which we haven't added so far.
- The KiCad IPC API (`kipy`) in versions 9 and 10 doesn't support the schematic
  editor — the data source for netlist/BOM/netclass remains file-based
  (`.net` + `.kicad_pro`) for the foreseeable future.

## Building an installer

```bash
pyinstaller --onefile --name KiCadNetExporter --paths . --distpath "D:\Utils" run.py
```
