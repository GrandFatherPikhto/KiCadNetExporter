"""
Watchdog следит за конкретными файлами из конфига (.net и .kicad_pro каждого
проекта), а не просто за расширением *.net в директории — так патч классов
в .kicad_pro тоже вызывает пересборку отчётов, даже если .net не менялся.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import AppConfig, ProjectConfig
from .pipeline import run_project

logger = logging.getLogger(__name__)


class _TrackedFileHandler(FileSystemEventHandler):
    def __init__(self, config: AppConfig, paused: threading.Event):
        super().__init__()
        self.config = config
        self.paused = paused
        self._last_run: dict[str, float] = {}
        self.watch_map: dict[str, ProjectConfig] = {}
        for project in config.projects:
            for raw_path in (project.netlist, project.kicad_project):
                p = Path(raw_path)
                if p.exists():
                    self.watch_map[str(p.resolve())] = project
                else:
                    logger.warning("Файл не найден (пока не слежу за ним): %s", raw_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        try:
            path = str(Path(event.src_path).resolve())
        except OSError:
            return

        project = self.watch_map.get(path)
        if project is None:
            return
        if self.paused.is_set():
            logger.debug("На паузе — пропускаю событие для %s", project.name)
            return

        now = time.time()
        if now - self._last_run.get(project.name, 0) < self.config.watch.debounce_sec:
            return
        self._last_run[project.name] = now

        time.sleep(self.config.watch.settle_delay_sec)  # дать KiCad дописать файл
        logger.info("Изменение: %s (проект %s)", path, project.name)
        try:
            run_project(project, self.config)
        except Exception:
            logger.exception("Пайплайн упал для проекта %s", project.name)


def run_watch_loop(config: AppConfig, stop_flag: threading.Event, paused: threading.Event) -> None:
    handler = _TrackedFileHandler(config, paused)
    observer = Observer()

    watched_dirs = {
        str(Path(p).resolve().parent)
        for project in config.projects
        for p in (project.netlist, project.kicad_project)
    }
    for d in watched_dirs:
        if Path(d).is_dir():
            observer.schedule(handler, path=d, recursive=False)
            logger.info("Слежу за директорией: %s", d)
        else:
            logger.warning("Директория не существует, слежение пропущено: %s", d)

    observer.start()
    try:
        while not stop_flag.is_set():
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
        logger.info("Наблюдатель остановлен")
