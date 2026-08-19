"""
Тестовые данные: синтетический иерархический проект.

Повторяет идеи test_sample/demo.* , но дополнен кейсами, которые нужны
именно юнит-тестам:
- многосекционные компоненты (U1A/U1B -> U1);
- компонент без footprint (C1);
- иерархические цепи (+3V3 на вложенном листе);
- unconnected / power / suspicious цепи;
- «плохой» escape в паттерне (\\CLK.*);
- паттерн, ссылающийся на необъявленный класс (Ghost);
- паттерн с некомпилируемым regex;
- правила трассировки классов (track_width/clearance).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# .net (sexp) — образец в стиле экспорта eeschema KiCad 10.
# ---------------------------------------------------------------------------
SAMPLE_NET = """\
(export (version "E")
  (design
    (source "demo.sch")
    (date "2026-07-11")
    (tool "Eeschema"))
  (components
    (comp (ref "R1")
      (value "10k")
      (footprint "Resistor_SMD:R_0603")
      (sheetpath (names "/") (tstamps "/")))
    (comp (ref "U1A")
      (value "STM32F103")
      (footprint "Package_QFP:LQFP-48")
      (sheetpath (names "/") (tstamps "/")))
    (comp (ref "U1B")
      (value "STM32F103")
      (footprint "Package_QFP:LQFP-48")
      (sheetpath (names "/") (tstamps "/")))
    (comp (ref "U2")
      (value "AMS1117-3.3")
      (footprint "Package_TO_SOT_SMD:SOT-223")
      (sheetpath (names "/Power/Filter/") (tstamps "/aaa/bbb/")))
    (comp (ref "C1")
      (value "100n")
      (footprint "")
      (sheetpath (names "/Power/Filter/") (tstamps "/aaa/bbb/"))))
  (libparts)
  (libraries)
  (nets
    (net (code "1") (name "+5V")
      (node (ref "R1") (pin "1"))
      (node (ref "U1A") (pin "12")))
    (net (code "2") (name "GND")
      (node (ref "R1") (pin "2"))
      (node (ref "U1B") (pin "13"))
      (node (ref "U2") (pin "1")))
    (net (code "3") (name "/Power/Filter/+3V3")
      (node (ref "U2") (pin "3"))
      (node (ref "C1") (pin "1")))
    (net (code "4") (name "/Power/Filter/CLK_OUT")
      (node (ref "U2") (pin "5")))
    (net (code "5") (name "unconnected-(U1-Pad14)")
      (node (ref "U1A") (pin "14")))
    (net (code "6") (name "USB_DP2")
      (node (ref "U1A") (pin "20"))
      (node (ref "U1B") (pin "20"))))
)
"""

# .net без секций design/components/nets — парсер должен вернуть пустую модель.
EMPTY_NET = """\
(export (version "E")
  (libparts)
  (libraries))
"""

# ---------------------------------------------------------------------------
# .kicad_pro (json).
# ---------------------------------------------------------------------------
SAMPLE_KICAD_PRO = """\
{
  "net_settings": {
    "classes": [
      {"name": "Default", "priority": 2147483647},
      {"name": "Power", "priority": 1,
       "track_width": 0.5, "clearance": 0.2,
       "via_diameter": 0.8, "via_drill": 0.4},
      {"name": "Clock", "priority": 2}
    ],
    "netclass_patterns": [
      {"netclass": "Power", "pattern": "(?i)^(GND|VCC|VDD|\\\\+\\\\d+V.*)$"},
      {"netclass": "Clock", "pattern": "\\\\CLK.*"},
      {"netclass": "Ghost", "pattern": "USB.*"},
      {"netclass": "Broken", "pattern": "([unclosed"}
    ]
  }
}
"""

# Паттерн "Broken" выше содержит невалидный regex — скомпилировать нельзя.

# Паттерны классификации — совпадают с дефолтами из config.py, но заданы явно,
# чтобы тесты не зависели от внутренних дефолтов модуля.
POWER_PATTERNS = [
    r"(?i)^GND$",
    r"(?i)^\+?\d+V\d*",
    r"(?i)VCC|VDD|VEE|VSS",
]
SUSPICIOUS_PATTERNS = [
    r"(?i)net-\(",
    r"(?i)[+-]\d+v",
    r"(?i)clk|clock",
    r"(?i)pwr|vcc|vdd|vee",
]
