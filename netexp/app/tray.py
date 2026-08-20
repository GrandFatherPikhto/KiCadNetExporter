"""
Иконка в трее (pystray) — единственный "UI" процесса, раз он живёт как
pythonw без консоли. Меню: открыть папку(и) вывода, открыть лог, пауза
слежения, добавить проект (tkinter-диалог в отдельном потоке), выход.
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

from .config import (
    AppConfig,
    ProjectConfig,
    append_project,
    validate_new_project,
)
from .pipeline import run_project
from .watcher import WatchHandle

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


def _show_add_project_dialog(config: AppConfig, config_path: Path | None,
                             watch_handle: WatchHandle | None) -> None:
    """Строит и показывает tkinter-диалог «Добавить проект» в отдельном потоке
    (свой tk.Tk() и mainloop внутри него). Главный поток занят
    pystray.Icon.run(), а Tk не любит переиспользование между потоками —
    поэтому весь UI создаётся и живёт здесь, в этом потоке."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.title("Добавить проект")
    root.resizable(False, False)

    def _pick_file(entry: tk.Entry, filetypes: list) -> None:
        path = filedialog.askopenfilename(parent=root, filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _pick_dir(entry: tk.Entry) -> None:
        path = filedialog.askdirectory(parent=root)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    frame = tk.Frame(root, padx=12, pady=12)
    frame.grid(sticky="nsew")

    name_var = tk.StringVar()
    pro_var = tk.StringVar()
    net_var = tk.StringVar()
    out_var = tk.StringVar()
    error_var = tk.StringVar()

    tk.Label(frame, text="Имя проекта:").grid(row=0, column=0, sticky="w")
    tk.Entry(frame, textvariable=name_var, width=60).grid(
        row=0, column=1, columnspan=2, sticky="we", pady=2)

    tk.Label(frame, text="Проект KiCad (.kicad_pro):").grid(row=1, column=0, sticky="w")
    pro_entry = tk.Entry(frame, textvariable=pro_var, width=60)
    pro_entry.grid(row=1, column=1, sticky="we", pady=2)
    tk.Button(frame, text="Обзор...", command=lambda: _pick_file(
        pro_entry, [("KiCad project", "*.kicad_pro"), ("Все файлы", "*.*")]
    )).grid(row=1, column=2, padx=(4, 0))

    tk.Label(frame, text="Нетлист (.net):").grid(row=2, column=0, sticky="w")
    net_entry = tk.Entry(frame, textvariable=net_var, width=60)
    net_entry.grid(row=2, column=1, sticky="we", pady=2)
    tk.Button(frame, text="Обзор...", command=lambda: _pick_file(
        net_entry, [("KiCad netlist", "*.net"), ("Все файлы", "*.*")]
    )).grid(row=2, column=2, padx=(4, 0))

    tk.Label(frame, text="Папка вывода (необязательно):").grid(row=3, column=0, sticky="w")
    out_entry = tk.Entry(frame, textvariable=out_var, width=60)
    out_entry.grid(row=3, column=1, sticky="we", pady=2)
    tk.Button(frame, text="Обзор...", command=lambda: _pick_dir(out_entry)).grid(
        row=3, column=2, padx=(4, 0))

    tk.Label(frame, textvariable=error_var, fg="#c0392b", justify="left",
             anchor="w", wraplength=520).grid(
        row=4, column=0, columnspan=3, sticky="we", pady=(4, 0))

    def on_submit() -> None:
        name = name_var.get().strip()
        kicad_project = pro_var.get().strip()
        netlist = net_var.get().strip()
        output_dir = out_var.get().strip()

        # Дефолты — те же, что в config.py::load_config.
        if not name and netlist:
            name = Path(netlist).stem
        if not output_dir and netlist:
            output_dir = str(Path(netlist).parent / "out")

        errors = validate_new_project(name, kicad_project, netlist, config.projects)
        if errors:
            error_var.set("\n".join(errors))
            return  # не закрываем диалог — даём поправить поля

        project = ProjectConfig(name=name, kicad_project=kicad_project,
                                netlist=netlist, output_dir=output_dir)
        try:
            if config_path is not None:
                append_project(config_path, project)
            config.projects.append(project)
            if watch_handle is not None and watch_handle.handler is not None:
                watch_handle.handler.register_project(project)
        except Exception:
            logger.exception("Не удалось сохранить проект %s — файл конфига не тронут", project.name)
            error_var.set("Не удалось сохранить проект в конфиг — см. лог.")
            return

        logger.info("Проект %s добавлен в конфиг и начинает отслеживаться", project.name)
        root.destroy()

        # Первичный прогон в этом же фоновом потоке — результат появляется сразу.
        try:
            run_project(project, config)
        except FileNotFoundError as e:
            logger.error("Первичный прогон пропущен для проекта %s: %s", project.name, e)
        except Exception:
            logger.exception("Первичный прогон упал для проекта %s", project.name)

    btns = tk.Frame(frame)
    btns.grid(row=5, column=1, columnspan=2, sticky="e", pady=(12, 0))
    tk.Button(btns, text="Отмена", command=root.destroy, width=10).pack(side="left", padx=(0, 8))
    tk.Button(btns, text="Добавить", command=on_submit, width=10).pack(side="left")

    root.mainloop()


def build_icon(config: AppConfig, stop_flag: threading.Event, paused: threading.Event,
               log_path: Path | None, config_path: Path | None = None,
               watch_handle: WatchHandle | None = None) -> pystray.Icon:
    """
    Вынесено из run_tray отдельно — нужно создать Icon ДО запуска потока
    watcher'а, чтобы передать в него ссылку на icon и звать icon.notify()
    прямо из watcher-потока при обнаружении устаревшего нетлиста (см.
    watcher.py: on_stale колбэк). pystray.notify() — обычная нативная
    ОС-нотификация, вызов из чужого потока штатно поддерживается на всех
    трёх бэкендах (win32/appindicator/darwin).

    config_path и watch_handle нужны пункту «Добавить проект...»: первый — чтобы
    дописать проект в YAML (с сохранением комментариев), второй — чтобы завести
    его в живом наблюдателе без перезапуска приложения.
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

    def on_add_project(icon, item):
        # pystray.Icon.run() занимает главный поток, Tk требует свой mainloop —
        # поэтому диалог открываем в отдельном потоке со своим tk.Tk().
        threading.Thread(
            target=_show_add_project_dialog,
            args=(config, config_path, watch_handle),
            daemon=True,
        ).start()

    def on_exit(icon, item):
        logger.info("Выход по команде из трея")
        stop_flag.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Открыть папку(и) вывода", on_open_outputs),
        pystray.MenuItem("Открыть лог", on_open_log, enabled=lambda item: bool(log_path)),
        pystray.MenuItem("Пауза", on_toggle_pause, checked=lambda item: paused.is_set()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Добавить проект...", on_add_project),
        pystray.MenuItem("Выход", on_exit),
    )
    return pystray.Icon("kicad-net-exporter", _make_icon_image(), "KiCad Net Exporter", menu)


def run_tray(config: AppConfig, stop_flag: threading.Event, paused: threading.Event, log_path: Path | None) -> None:
    build_icon(config, stop_flag, paused, log_path).run()
