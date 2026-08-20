"""Точка входа. Запуск: python -m netexp.app.main config.yaml [--once] [--no-tray]"""
from __future__ import annotations

import argparse
import logging
import threading
from pathlib import Path

from .config import load_config
from .logging_setup import setup_logging
from .pipeline import run_project
from .watcher import WatchHandle, run_watch_loop

logger = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="KiCad Net Exporter — упрощение и аудит нетлистов")
    ap.add_argument("config", nargs='?', default="KiCadNetExporter.yaml", help="Путь к YAML-конфигу")
    ap.add_argument("--once", action="store_true", help="Прогнать все проекты один раз и выйти (без watch/трея)")
    ap.add_argument("--no-tray", action="store_true", help="Не показывать иконку в трее")
    args = ap.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    log_path = setup_logging(config.logging, base_dir=config_path.parent)

    if args.once:
        for project in config.projects:
            try:
                run_project(project, config)
            except FileNotFoundError as e:
                logger.error("Проект %s пропущен: %s", project.name, e)
        return

    # первичный прогон при старте — чтобы отчёты были свежими сразу,
    # а не только после первого изменения файла
    for project in config.projects:
        try:
            run_project(project, config)
        except FileNotFoundError as e:
            logger.error("Первичный прогон пропущен для проекта %s: %s", project.name, e)
        except Exception:
            logger.exception("Первичный прогон упал для проекта %s", project.name)

    stop_flag = threading.Event()
    paused = threading.Event()

    # Shared-объект между main/watcher/tray: заполняется в run_watch_loop живым
    # handler/observer, чтобы пункт «Добавить проект...» мог завести новый
    # проект в слежении без перезапуска приложения.
    watch_handle = WatchHandle()

    icon = None
    if config.tray.enabled and not args.no_tray:
        try:
            from .tray import build_icon
            icon = build_icon(config, stop_flag, paused, log_path,
                              config_path=config_path, watch_handle=watch_handle)
        except Exception:
            logger.exception("Не удалось создать иконку в трее — работаю без неё")

    def on_stale(project_name: str, message: str) -> None:
        if icon is not None:
            try:
                icon.notify(message, f"Нетлист устарел: {project_name}")
            except Exception:
                logger.exception("Не удалось показать уведомление трея")

    watch_thread = threading.Thread(
        target=run_watch_loop,
        args=(config, stop_flag, paused, on_stale, watch_handle),
        daemon=True,
    )
    watch_thread.start()
    logger.info("Наблюдатель запущен")

    if icon is not None:
        icon.run()
    else:
        try:
            while not stop_flag.is_set():
                stop_flag.wait(1)
        except KeyboardInterrupt:
            stop_flag.set()

    watch_thread.join(timeout=5)


if __name__ == "__main__":
    main()