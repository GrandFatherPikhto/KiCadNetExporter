"""Точка входа. Запуск: python -m netexp.app.main config.yaml [--once] [--no-tray]"""
from __future__ import annotations

import argparse
import logging
import threading
from pathlib import Path

from .config import load_config
from .logging_setup import setup_logging
from .pipeline import run_project
from .watcher import run_watch_loop

logger = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="KiCad Net Exporter — упрощение и аудит нетлистов")
    ap.add_argument("config", help="Путь к YAML-конфигу")
    ap.add_argument("--once", action="store_true", help="Прогнать все проекты один раз и выйти (без watch/трея)")
    ap.add_argument("--no-tray", action="store_true", help="Не показывать иконку в трее")
    args = ap.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    log_path = setup_logging(config.logging, base_dir=config_path.parent)

    if args.once:
        for project in config.projects:
            run_project(project, config)
        return

    # первичный прогон при старте — чтобы отчёты были свежими сразу,
    # а не только после первого изменения файла
    for project in config.projects:
        try:
            run_project(project, config)
        except Exception:
            logger.exception("Первичный прогон упал для проекта %s", project.name)

    stop_flag = threading.Event()
    paused = threading.Event()

    watch_thread = threading.Thread(
        target=run_watch_loop, args=(config, stop_flag, paused), daemon=True
    )
    watch_thread.start()
    logger.info("Наблюдатель запущен")

    if config.tray.enabled and not args.no_tray:
        try:
            from .tray import run_tray  # импорт тоже может упасть (нет GUI-бэкенда) — ловим и его

            run_tray(config, stop_flag, paused, log_path)
        except Exception:
            logger.exception("Не удалось запустить иконку в трее — работаю без неё")
            try:
                while not stop_flag.is_set():
                    stop_flag.wait(1)
            except KeyboardInterrupt:
                stop_flag.set()
    else:
        try:
            while not stop_flag.is_set():
                stop_flag.wait(1)
        except KeyboardInterrupt:
            stop_flag.set()

    watch_thread.join(timeout=5)


if __name__ == "__main__":
    main()
