"""Логирование настраивается из YAML-конфига (уровень/файл/ротация/консоль)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LoggingConfig


def setup_logging(cfg: LoggingConfig, base_dir: Path) -> Path | None:
    """Возвращает путь к лог-файлу (или None, если файл отключён)."""
    level = getattr(logging, str(cfg.level).upper(), logging.INFO)
    handlers: list[logging.Handler] = []
    log_path: Path | None = None

    if cfg.file:
        log_path = Path(cfg.file)
        if not log_path.is_absolute():
            log_path = base_dir / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_path, maxBytes=cfg.max_bytes, backupCount=cfg.backup_count, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        handlers.append(fh)

    if cfg.console:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        handlers.append(ch)

    # Библиотека watchdog на DEBUG крайне многословна и, если лог-файл
    # лежит внутри отслеживаемой директории, это может уйти в петлю обратной
    # связи (запись в лог -> событие изменения файла -> ещё запись в лог).
    # Поэтому её собственный логгер всегда прижимаем к WARNING, вне
    # зависимости от уровня, заданного для приложения.
    logging.getLogger("watchdog").setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in handlers:
        root.addHandler(h)

    return log_path
