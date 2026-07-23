"""
Иконка в трее (pystray) — единственный "UI" процесса, раз он живёт как
pythonw без консоли. Меню: открыть папку(и) вывода, открыть лог, пауза
слежения, выход.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

from .config import AppConfig

logger = logging.getLogger(__name__)


def _make_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(30, 100, 200, 255))
    d.text((22, 20), "N", fill="white")
    return img


def _open_path(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        logger.exception("Не удалось открыть %s", path)


def build_icon(config: AppConfig, stop_flag: threading.Event, paused: threading.Event,
               log_path: Path | None) -> pystray.Icon:
    """
    Вынесено из run_tray отдельно — нужно создать Icon ДО запуска потока
    watcher'а, чтобы передать в него ссылку на icon и звать icon.notify()
    прямо из watcher-потока при обнаружении устаревшего нетлиста (см.
    watcher.py: on_stale колбэк). pystray.notify() — обычная нативная
    ОС-нотификация, вызов из чужого потока штатно поддерживается на всех
    трёх бэкендах (win32/appindicator/darwin).
    """
    def on_open_outputs(icon, item):
        for project in config.projects:
            _open_path(Path(project.output_dir))

    def on_open_log(icon, item):
        if log_path and log_path.exists():
            _open_path(log_path)

    def on_toggle_pause(icon, item):
        if paused.is_set():
            paused.clear()
            logger.info("Слежение возобновлено (из трея)")
        else:
            paused.set()
            logger.info("Слежение поставлено на паузу (из трея)")

    def on_exit(icon, item):
        logger.info("Выход по команде из трея")
        stop_flag.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Открыть папку(и) вывода", on_open_outputs),
        pystray.MenuItem("Открыть лог", on_open_log, enabled=lambda item: bool(log_path)),
        pystray.MenuItem("Пауза", on_toggle_pause, checked=lambda item: paused.is_set()),
        pystray.MenuItem("Выход", on_exit),
    )
    return pystray.Icon("kicad-net-exporter", _make_icon_image(), "KiCad Net Exporter", menu)


def run_tray(config: AppConfig, stop_flag: threading.Event, paused: threading.Event, log_path: Path | None) -> None:
    build_icon(config, stop_flag, paused, log_path).run()