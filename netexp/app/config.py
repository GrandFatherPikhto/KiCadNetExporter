"""
Единый YAML-конфиг (заменяет старую пару config.yaml + config.yml).
Комментарии в YAML — это и была причина не брать JSON для конфига.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_POWER_PATTERNS = [
    r"(?i)^GND$",
    r"(?i)^\+?\d+V\d*",
    r"(?i)VCC|VDD|VEE|VSS",
]
_DEFAULT_SUSPICIOUS_PATTERNS = [
    r"(?i)net-\(",
    r"(?i)[+-]\d+v",
    r"(?i)clk|clock",
    r"(?i)pwr|vcc|vdd|vee",
]


@dataclass
class ProjectConfig:
    name: str
    kicad_project: str
    netlist: str
    output_dir: str


@dataclass
class OutputConfig:
    formats: list[str] = field(default_factory=lambda: ["txt", "json"])
    raw_txt_copy: bool = False
    diff: bool = True


@dataclass
class ClassificationConfig:
    power_patterns: list[str] = field(default_factory=lambda: list(_DEFAULT_POWER_PATTERNS))
    suspicious_patterns: list[str] = field(default_factory=lambda: list(_DEFAULT_SUSPICIOUS_PATTERNS))


@dataclass
class WatchConfig:
    enabled: bool = True
    debounce_sec: float = 1.0
    settle_delay_sec: float = 0.2


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "kicad_net_exporter.log"
    max_bytes: int = 1_048_576
    backup_count: int = 3
    console: bool = True


@dataclass
class TrayConfig:
    enabled: bool = True


@dataclass
class AppConfig:
    projects: list[ProjectConfig]
    output: OutputConfig
    classification: ClassificationConfig
    watch: WatchConfig
    logging: LoggingConfig
    tray: TrayConfig


def _get(d: dict[str, Any], key: str, default: Any) -> Any:
    v = d.get(key)
    return default if v is None else v


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    projects_raw = raw.get("projects")
    if not projects_raw:
        raise ValueError(f"В конфиге {path} не задано ни одного проекта (секция 'projects')")

    projects = [
        ProjectConfig(
            name=_get(p, "name", Path(p["netlist"]).stem),
            kicad_project=p["kicad_project"],
            netlist=p["netlist"],
            output_dir=_get(p, "output_dir", str(Path(p["netlist"]).parent / "out")),
        )
        for p in projects_raw
    ]

    out_raw = raw.get("output", {}) or {}
    output = OutputConfig(
        formats=_get(out_raw, "formats", ["txt", "json"]),
        raw_txt_copy=_get(out_raw, "raw_txt_copy", False),
        diff=_get(out_raw, "diff", True),
    )

    cls_raw = raw.get("classification", {}) or {}
    classification = ClassificationConfig(
        power_patterns=_get(cls_raw, "power_patterns", list(_DEFAULT_POWER_PATTERNS)),
        suspicious_patterns=_get(cls_raw, "suspicious_patterns", list(_DEFAULT_SUSPICIOUS_PATTERNS)),
    )

    watch_raw = raw.get("watch", {}) or {}
    watch = WatchConfig(
        enabled=_get(watch_raw, "enabled", True),
        debounce_sec=_get(watch_raw, "debounce_sec", 1.0),
        settle_delay_sec=_get(watch_raw, "settle_delay_sec", 0.2),
    )

    log_raw = raw.get("logging", {}) or {}
    logging_cfg = LoggingConfig(
        level=_get(log_raw, "level", "INFO"),
        file=_get(log_raw, "file", "kicad_net_exporter.log"),
        max_bytes=_get(log_raw, "max_bytes", 1_048_576),
        backup_count=_get(log_raw, "backup_count", 3),
        console=_get(log_raw, "console", True),
    )

    tray_raw = raw.get("tray", {}) or {}
    tray = TrayConfig(enabled=_get(tray_raw, "enabled", True))

    return AppConfig(
        projects=projects,
        output=output,
        classification=classification,
        watch=watch,
        logging=logging_cfg,
        tray=tray,
    )
