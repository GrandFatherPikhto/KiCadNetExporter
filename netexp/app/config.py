"""
Единый YAML-конфиг (заменяет старую пару config.yaml + config.yml).
Комментарии в YAML — это и была причина не брать JSON для конфига.
"""
from __future__ import annotations

import os
import tempfile
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


def validate_new_project(name: str, kicad_project: str, netlist: str,
                         existing: list[ProjectConfig],
                         exclude_name: str | None = None) -> list[str]:
    """Проверка данных нового проекта перед добавлением (через окно трея).

    exclude_name — имя проекта, которое при проверке дубликата имени надо
    игнорировать (сам редактируемый проект при переименовании): переименование
    в своё же текущее имя не должно считаться дублем.

    Возвращает список ошибок (пустой список — всё в порядке). Чистая функция
    без Tk-зависимостей, чтобы её можно было тестировать отдельно от UI.
    """
    errors: list[str] = []
    if not name:
        errors.append("Не задано имя проекта")
    if not kicad_project or not Path(kicad_project).is_file():
        errors.append("Файл проекта (.kicad_pro) не найден — проверьте путь")
    if not netlist or not Path(netlist).is_file():
        errors.append("Файл нетлиста (.net) не найден — проверьте путь")
    if any(p.name == name for p in existing if p.name != exclude_name):
        errors.append(f"Проект с именем «{name}» уже есть в конфиге")
    return errors


def append_project(config_path: Path, project: ProjectConfig) -> None:
    """Дописывает проект в YAML-конфиг, сохраняя комментарии и форматирование
    остального файла (round-trip через ruamel.yaml).

    Перед перезаписью делает бэкап <имя>.yaml.bak, а саму запись выполняет
    через временный файл + os.replace() — оригинал не затирается напрямую,
    если что-то пойдёт не так.
    """
    from ruamel.yaml import YAML

    config_path = Path(config_path)

    yaml_rt = YAML(typ="rt")
    yaml_rt.preserve_quotes = True

    with open(config_path, encoding="utf-8") as f:
        doc = yaml_rt.load(f)

    projects = doc.get("projects")
    if projects is None:
        projects = []
        doc["projects"] = projects
    projects.append({
        "name": project.name,
        "kicad_project": project.kicad_project,
        "netlist": project.netlist,
        "output_dir": project.output_dir,
    })

    # Бэкап текущего файла — при сбое записи останется возможность откатиться.
    backup_path = config_path.with_name(config_path.name + ".bak")
    backup_path.write_bytes(config_path.read_bytes())

    # Пишем через временный файл в той же директории, затем атомарно заменяем.
    fd, tmp_name = tempfile.mkstemp(dir=str(config_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml_rt.dump(doc, f)
        os.replace(tmp_name, config_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def remove_project(config_path: Path, name: str) -> None:
    """Удаляет проект из YAML-конфига по имени, сохраняя комментарии и
    форматирование остального файла. Зеркало append_project: бэкап
    <имя>.bak, атомарная запись через temp-файл + os.replace().

    Если проекта с таким именем в файле нет — поднимает ValueError (конфиг
    при этом не трогается, бэкап не создаётся).
    """
    from ruamel.yaml import YAML

    config_path = Path(config_path)

    yaml_rt = YAML(typ="rt")
    yaml_rt.preserve_quotes = True

    with open(config_path, encoding="utf-8") as f:
        doc = yaml_rt.load(f)

    projects = doc.get("projects")
    target = None
    if projects is not None:
        for p in projects:
            if p.get("name") == name:
                target = p
                break
    if target is None:
        raise ValueError(f"Проект «{name}» не найден в конфиге {config_path}")

    projects.remove(target)

    # Бэкап текущего файла — при сбое записи останется возможность откатиться.
    backup_path = config_path.with_name(config_path.name + ".bak")
    backup_path.write_bytes(config_path.read_bytes())

    # Пишем через временный файл в той же директории, затем атомарно заменяем.
    fd, tmp_name = tempfile.mkstemp(dir=str(config_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml_rt.dump(doc, f)
        os.replace(tmp_name, config_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def update_project(config_path: Path, old_name: str, project: ProjectConfig) -> None:
    """Обновляет существующий проект в YAML (в т.ч. переименование), сохраняя
    комментарии/форматирование остального файла. Ищет запись по old_name и
    правит её поля на месте (не удаляет+вставляет — так исходные комментарии
    у конкретной записи, если есть, сохраняются надёжнее).

    Тот же паттерн, что append_project/remove_project: бэкап <имя>.bak,
    атомарная запись через temp-файл + os.replace(). Если проекта с old_name
    в файле нет — ValueError (конфиг не трогается).
    """
    from ruamel.yaml import YAML

    config_path = Path(config_path)

    yaml_rt = YAML(typ="rt")
    yaml_rt.preserve_quotes = True

    with open(config_path, encoding="utf-8") as f:
        doc = yaml_rt.load(f)

    projects = doc.get("projects")
    target = None
    if projects is not None:
        for p in projects:
            if p.get("name") == old_name:
                target = p
                break
    if target is None:
        raise ValueError(f"Проект «{old_name}» не найден в конфиге {config_path}")

    target["name"] = project.name
    target["kicad_project"] = project.kicad_project
    target["netlist"] = project.netlist
    target["output_dir"] = project.output_dir

    # Бэкап текущего файла — при сбое записи останется возможность откатиться.
    backup_path = config_path.with_name(config_path.name + ".bak")
    backup_path.write_bytes(config_path.read_bytes())

    # Пишем через временный файл в той же директории, затем атомарно заменяем.
    fd, tmp_name = tempfile.mkstemp(dir=str(config_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml_rt.dump(doc, f)
        os.replace(tmp_name, config_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
