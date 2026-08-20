"""
Watchdog следит за конкретными файлами из конфига (.net и .kicad_pro каждого
проекта), а не просто за расширением *.net в директории — так патч классов
в .kicad_pro тоже вызывает пересборку отчётов, даже если .net не менялся.

Дополнительно следит за *.kicad_sch рядом с каждым проектом — НЕ для
перезапуска пайплайна (netexp схему не читает и не может перегенерировать
нетлист сам, это делает только KiCad через Export Netlist), а чтобы
предупредить: "схему поправили, а нетлист — нет" (см. on_stale). Та же
эвристика по mtime, что и в kicadspoke.cloner.extract._check_netlist_freshness
— не доказательство, а сигнал, поэтому не блокирует пайплайн, только уведомляет.
"""
from __future__ import annotations

import glob
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import AppConfig, ProjectConfig
from .pipeline import run_project

logger = logging.getLogger(__name__)

_STALE_GRACE_SEC = 30.0  # не уведомлять сразу — дать время дописать/сохранить схему нормально


class _TrackedFileHandler(FileSystemEventHandler):
    def __init__(self, config: AppConfig, paused: threading.Event,
                on_stale: Optional[Callable[[str, str], None]] = None):
        super().__init__()
        self.config = config
        self.paused = paused
        self.on_stale = on_stale
        self._last_run: dict[str, float] = {}
        self.watch_map: dict[str, ProjectConfig] = {}
        self.sch_watch_map: dict[str, ProjectConfig] = {}
        self._sch_mtime: dict[str, float] = {}          # project.name -> mtime схемы на момент правки
        self._notified_stale: dict[str, bool] = {}       # project.name -> уже уведомили про этот эпизод
        self.observer: Optional[Observer] = None         # выставляется в run_watch_loop
        self.watched_dirs: set[str] = set()              # директории, уже запланированные в observer
        self.frozen: set[str] = set()                    # имена замороженных проектов (только в памяти)

        for project in config.projects:
            for raw_path in (project.netlist, project.kicad_project):
                p = Path(raw_path)
                if p.exists():
                    self.watch_map[str(p.resolve())] = project
                else:
                    logger.warning("Файл не найден (пока не слежу за ним): %s", raw_path)

            proj_dir = Path(project.kicad_project).resolve().parent
            for sch in glob.glob(str(proj_dir / "*.kicad_sch")):
                self.sch_watch_map[str(Path(sch).resolve())] = project

    def register_project(self, project: ProjectConfig) -> None:
        """Регистрирует новый проект в живом наблюдателе без перезапуска
        приложения: добавляет пути в watch_map/sch_watch_map и, если директория
        ещё не отслеживается, планирует её в observer. Вызывается из фонового
        потока диалога — только простые thread-safe операции (вставки в словари
        и observer.schedule), без обращения к UI из чужого потока."""
        for raw_path in (project.netlist, project.kicad_project):
            p = Path(raw_path)
            if p.exists():
                self.watch_map[str(p.resolve())] = project
            else:
                logger.warning("Файл не найден (пока не слежу за ним): %s", raw_path)

        proj_dir = Path(project.kicad_project).resolve().parent
        for sch in glob.glob(str(proj_dir / "*.kicad_sch")):
            self.sch_watch_map[str(Path(sch).resolve())] = project

        for raw_path in (project.netlist, project.kicad_project):
            p = Path(raw_path)
            if not p.exists():
                continue
            d = str(p.resolve().parent)
            if d in self.watched_dirs:
                continue
            if not Path(d).is_dir():
                logger.warning("Директория не существует, слежение пропущено: %s", d)
                continue
            if self.observer is not None:
                self.observer.schedule(self, path=d, recursive=False)
            self.watched_dirs.add(d)
            logger.info("Слежу за директорией (новый проект): %s", d)

    def unregister_project(self, name: str) -> None:
        """Убирает проект из watch-карт по имени (записи, чьё значение
        .name == name). Директории из observer НЕ отписываем: unschedule требует
        хранить ObservedWatch (которого сейчас нет), а в одной директории могут
        лежать несколько проектов — отписка сломала бы соседей. Оставшийся
        «пустой» watch безвреден: события просто не находят совпадения в
        watch_map и игнорируются."""
        for mapping in (self.watch_map, self.sch_watch_map):
            for key in [k for k, v in mapping.items() if v.name == name]:
                del mapping[key]

    def set_frozen(self, name: str, frozen: bool) -> None:
        """Заморозить/разморозить конкретный проект (только в памяти, не
        персистится — как общая «Пауза» из трея)."""
        if frozen:
            self.frozen.add(name)
            logger.info("Проект %s заморожен (из окна настроек)", name)
        else:
            self.frozen.discard(name)
            logger.info("Проект %s разморожен (из окна настроек)", name)

    def is_frozen(self, name: str) -> bool:
        return name in self.frozen

    def _check_stale(self, project: ProjectConfig) -> None:
        """Схема новее нетлиста дольше grace-периода — уведомить один раз за эпизод."""
        net_path = Path(project.netlist)
        if not net_path.exists():
            return
        net_mtime = net_path.stat().st_mtime
        sch_mtime = self._sch_mtime.get(project.name)
        if sch_mtime is None or sch_mtime <= net_mtime:
            self._notified_stale[project.name] = False
            return
        if time.time() - sch_mtime < _STALE_GRACE_SEC:
            return  # ещё в пределах grace-периода, не спешим
        if self._notified_stale.get(project.name):
            return  # уже предупредили про этот конкретный эпизод устаревания
        self._notified_stale[project.name] = True
        logger.warning("Схема проекта %s новее нетлиста дольше %.0f сек — нетлист устарел",
                       project.name, _STALE_GRACE_SEC)
        if self.on_stale:
            self.on_stale(project.name,
                         f"Схема изменена, а нетлист не переэкспортирован. "
                         f"Export Netlist в eeschema для проекта {project.name!r}.")

    def on_modified(self, event):
        if event.is_directory:
            return
        try:
            path = str(Path(event.src_path).resolve())
        except OSError:
            return

        if path in self.sch_watch_map:
            project = self.sch_watch_map[path]
            self._sch_mtime[project.name] = time.time()
            # Не перезапускаем пайплайн — только фиксируем момент правки схемы,
            # проверка "устарел ли нетлист" происходит по таймеру ниже.
            return

        project = self.watch_map.get(path)
        if project is None:
            return
        if self.paused.is_set() or project.name in self.frozen:
            reason = "общая пауза" if self.paused.is_set() else "проект заморожен"
            logger.debug("Пропускаю событие для %s (%s)", project.name, reason)
            return

        now = time.time()
        if now - self._last_run.get(project.name, 0) < self.config.watch.debounce_sec:
            return
        self._last_run[project.name] = now

        time.sleep(self.config.watch.settle_delay_sec)  # дать KiCad дописать файл
        logger.info("Изменение: %s (проект %s)", path, project.name)
        # Нетлист реально обновился — эпизод устаревания закрыт.
        self._notified_stale[project.name] = False
        try:
            run_project(project, self.config)
        except FileNotFoundError as e:
            logger.error("Пайплайн пропущен для проекта %s: %s", project.name, e)
        except Exception:
            logger.exception("Пайплайн упал для проекта %s", project.name)


@dataclass
class WatchHandle:
    """Небольшой shared-объект между main.py / watcher.py / tray.py: живой
    handler и observer наблюдателя. Нужен, чтобы добавлять новые проекты в
    слежение без перезапуска приложения (см. tray.py: on_add_project).
    Заполняется внутри run_watch_loop, когда наблюдатель поднимается."""
    handler: Optional[_TrackedFileHandler] = None
    observer: Optional[Observer] = None


def run_watch_loop(config: AppConfig, stop_flag: threading.Event, paused: threading.Event,
                   on_stale: Optional[Callable[[str, str], None]] = None,
                   handle: Optional[WatchHandle] = None) -> None:
    handler = _TrackedFileHandler(config, paused, on_stale=on_stale)
    observer = Observer()
    if handle is not None:
        handle.handler = handler
        handle.observer = observer
        handler.observer = observer

    watched_dirs = {
        str(Path(p).resolve().parent)
        for project in config.projects
        for p in (project.netlist, project.kicad_project)
    }
    for d in watched_dirs:
        if Path(d).is_dir():
            observer.schedule(handler, path=d, recursive=False)
            handler.watched_dirs.add(d)
            logger.info("Слежу за директорией: %s", d)
        else:
            logger.warning("Директория не существует, слежение пропущено: %s", d)

    observer.start()
    try:
        while not stop_flag.is_set():
            for project in config.projects:
                handler._check_stale(project)
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
        logger.info("Наблюдатель остановлен")