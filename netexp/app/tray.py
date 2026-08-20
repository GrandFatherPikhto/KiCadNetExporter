"""
Иконка в трее (pystray) — единственный "UI" процесса, раз он живёт как
pythonw без консоли. Меню: открыть папку(и) вывода, открыть лог, пауза
слежения, настройки (окно управления проектами в отдельном потоке), выход.
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
    remove_project,
    update_project,
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


def _build_project_fields(parent) -> tuple[dict[str, tk.StringVar], dict[str, tk.Entry]]:
    """Строит блок полей проекта (имя, .kicad_pro, .net, папка вывода) с
    кнопками «Обзор...» внутри parent. Возвращает (vars, entries) — словари
    StringVar и Entry по именам полей.

    Единый источник вёрстки: используется и диалогом добавления, и окном
    настроек, чтобы не дублировать код.
    """
    import tkinter as tk
    from tkinter import filedialog

    def _pick_file(entry: tk.Entry, filetypes: list) -> None:
        path = filedialog.askopenfilename(parent=parent.winfo_toplevel(), filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _pick_dir(entry: tk.Entry) -> None:
        path = filedialog.askdirectory(parent=parent.winfo_toplevel())
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    vars_: dict[str, tk.StringVar] = {
        "name": tk.StringVar(),
        "kicad_project": tk.StringVar(),
        "netlist": tk.StringVar(),
        "output_dir": tk.StringVar(),
    }
    entries: dict[str, tk.Entry] = {}

    tk.Label(parent, text="Имя проекта:").grid(row=0, column=0, sticky="w")
    entries["name"] = tk.Entry(parent, textvariable=vars_["name"], width=48)
    entries["name"].grid(row=0, column=1, columnspan=2, sticky="we", pady=2)

    tk.Label(parent, text="Проект KiCad (.kicad_pro):").grid(row=1, column=0, sticky="w")
    entries["kicad_project"] = tk.Entry(parent, textvariable=vars_["kicad_project"], width=48)
    entries["kicad_project"].grid(row=1, column=1, sticky="we", pady=2)
    tk.Button(parent, text="Обзор...", command=lambda: _pick_file(
        entries["kicad_project"], [("KiCad project", "*.kicad_pro"), ("Все файлы", "*.*")]
    )).grid(row=1, column=2, padx=(4, 0))

    tk.Label(parent, text="Нетлист (.net):").grid(row=2, column=0, sticky="w")
    entries["netlist"] = tk.Entry(parent, textvariable=vars_["netlist"], width=48)
    entries["netlist"].grid(row=2, column=1, sticky="we", pady=2)
    tk.Button(parent, text="Обзор...", command=lambda: _pick_file(
        entries["netlist"], [("KiCad netlist", "*.net"), ("Все файлы", "*.*")]
    )).grid(row=2, column=2, padx=(4, 0))

    tk.Label(parent, text="Папка вывода (необязательно):").grid(row=3, column=0, sticky="w")
    entries["output_dir"] = tk.Entry(parent, textvariable=vars_["output_dir"], width=48)
    entries["output_dir"].grid(row=3, column=1, sticky="we", pady=2)
    tk.Button(parent, text="Обзор...", command=lambda: _pick_dir(entries["output_dir"])).grid(
        row=3, column=2, padx=(4, 0))

    return vars_, entries


def _show_settings_window(config: AppConfig, config_path: Path | None,
                          watch_handle: WatchHandle | None) -> None:
    """Окно «Настройки» — управление проектами. В отдельном потоке со своим
    tk.Tk() (главный поток занят pystray.Icon.run(), а Tk не любит
    переиспользование между потоками).

    Слева — список проектов со статусом заморозки, справа — поля проекта,
    между ними перетаскиваемый ttk.PanedWindow-сплиттер. Три режима: new
    (поля пустые/редактируемые, «Добавить»), selected (поля только чтение,
    «Изменить»/«Удалить»/«Заморозить»), editing (поля редактируемые,
    «Сохранить»/«Отмена»).
    """
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("Настройки — проекты KiCad Net Exporter")
    root.geometry("920x440")          # начальный размер
    root.minsize(640, 320)            # не даём схлопнуться в кашу при ресайзе
    root.resizable(True, True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    main = tk.Frame(root, padx=12, pady=12)
    main.grid(sticky="nsew")
    main.columnconfigure(0, weight=1)
    main.rowconfigure(0, weight=1)

    def handler():
        return watch_handle.handler if watch_handle is not None else None

    # ---------- сплиттер: слева список, справа поля ----------
    paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
    paned.grid(row=0, column=0, sticky="nsew")

    left = ttk.Frame(paned)
    right = tk.Frame(paned)
    paned.add(left, weight=1)
    paned.add(right, weight=2)
    left.columnconfigure(0, weight=1)
    left.rowconfigure(1, weight=1)
    right.columnconfigure(1, weight=1)

    ttk.Label(left, text="Проекты:").grid(row=0, column=0, sticky="w", pady=(0, 4))
    tree = ttk.Treeview(left, columns=("status",), show="tree headings",
                        selectmode="browse", height=14)
    tree.heading("#0", text="Проект")
    tree.heading("status", text="Статус")
    tree.column("#0", width=240, anchor="w")
    tree.column("status", width=110, anchor="center")
    tree.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)

    field_vars, field_entries = _build_project_fields(right)

    error_var = tk.StringVar()
    tk.Label(right, textvariable=error_var, fg="#c0392b", justify="left",
             anchor="w", wraplength=440).grid(
        row=4, column=0, columnspan=3, sticky="we", pady=(4, 0))
    hint_var = tk.StringVar()
    tk.Label(right, textvariable=hint_var, fg="#555555", justify="left",
             anchor="w", wraplength=440).grid(
        row=5, column=0, columnspan=3, sticky="we", pady=(2, 0))

    # ---------- кнопки ----------
    btn_frame = tk.Frame(right)
    btn_frame.grid(row=6, column=0, columnspan=3, sticky="e", pady=(12, 0))
    add_btn = tk.Button(btn_frame, text="Добавить", width=10)
    edit_btn = tk.Button(btn_frame, text="Изменить", width=10)
    save_btn = tk.Button(btn_frame, text="Сохранить", width=10)
    cancel_btn = tk.Button(btn_frame, text="Отмена", width=10)
    del_btn = tk.Button(btn_frame, text="Удалить", width=10)
    freeze_btn = tk.Button(btn_frame, text="Заморозить", width=10)
    for b in (add_btn, edit_btn, save_btn, cancel_btn, del_btn, freeze_btn):
        b.pack(side="left", padx=(0, 6))

    # Имя проекта, с которого начали правку (замыкание): нужно, чтобы при
    # сохранении понять, какую запись обновлять, даже если имя переименовали.
    editing_original_name: list[str | None] = [None]

    def _selected_name() -> str | None:
        sel = tree.selection()
        if not sel:
            return None
        return tree.item(sel[0], "text")

    def _is_frozen(name: str) -> bool:
        h = handler()
        return bool(h is not None and h.is_frozen(name))

    def _find_project(name: str) -> ProjectConfig | None:
        return next((p for p in config.projects if p.name == name), None)

    def _refresh_list() -> None:
        tree.delete(*tree.get_children())
        for project in config.projects:
            status = "⏸ заморожен" if _is_frozen(project.name) else "▶ активен"
            tree.insert("", "end", text=project.name, values=(status,))

    def _select_item_by_name(name: str) -> None:
        for item in tree.get_children():
            if tree.item(item, "text") == name:
                tree.selection_set(item)
                tree.focus(item)
                break

    def _set_buttons(*, add=False, edit=False, save=False, cancel=False,
                     delete=False, freeze=False, freeze_text="Заморозить") -> None:
        add_btn.config(state="normal" if add else "disabled")
        edit_btn.config(state="normal" if edit else "disabled")
        save_btn.config(state="normal" if save else "disabled")
        cancel_btn.config(state="normal" if cancel else "disabled")
        del_btn.config(state="normal" if delete else "disabled")
        freeze_btn.config(state="normal" if freeze else "disabled",
                          text=freeze_text)

    def _reset_to_new_mode() -> None:
        editing_original_name[0] = None
        tree.selection_remove(tree.selection())
        for var in field_vars.values():
            var.set("")
        for entry in field_entries.values():
            entry.config(state="normal")
        error_var.set("")
        hint_var.set("")
        _set_buttons(add=True)

    def _enter_selected_mode(project: ProjectConfig) -> None:
        editing_original_name[0] = None
        field_vars["name"].set(project.name)
        field_vars["kicad_project"].set(project.kicad_project)
        field_vars["netlist"].set(project.netlist)
        field_vars["output_dir"].set(project.output_dir)
        for entry in field_entries.values():
            entry.config(state="readonly")
        error_var.set("")
        hint_var.set("")
        frozen = _is_frozen(project.name)
        _set_buttons(edit=True, delete=True, freeze=True,
                     freeze_text="Разморозить" if frozen else "Заморозить")

    def _enter_editing_mode(project: ProjectConfig) -> None:
        editing_original_name[0] = project.name
        field_vars["name"].set(project.name)
        field_vars["kicad_project"].set(project.kicad_project)
        field_vars["netlist"].set(project.netlist)
        field_vars["output_dir"].set(project.output_dir)
        for entry in field_entries.values():
            entry.config(state="normal")
        error_var.set("")
        hint_var.set("Правка папки вывода не переносит уже сгенерированные "
                     "файлы — старые отчёты останутся в прежней папке.")
        _set_buttons(save=True, cancel=True)

    def on_select(_event=None) -> None:
        if editing_original_name[0] is not None:
            return  # в режиме правки не переключаемся на другой проект
        name = _selected_name()
        project = _find_project(name) if name else None
        if project is None:
            _reset_to_new_mode()
        else:
            _enter_selected_mode(project)

    tree.bind("<<TreeviewSelect>>", on_select)

    def on_add() -> None:
        name = field_vars["name"].get().strip()
        kicad_project = field_vars["kicad_project"].get().strip()
        netlist = field_vars["netlist"].get().strip()
        output_dir = field_vars["output_dir"].get().strip()

        # Дефолты — те же, что в config.py::load_config.
        if not name and netlist:
            name = Path(netlist).stem
        if not output_dir and netlist:
            output_dir = str(Path(netlist).parent / "out")

        errors = validate_new_project(name, kicad_project, netlist, config.projects)
        if errors:
            error_var.set("\n".join(errors))
            return  # окно остаётся открытым — даём поправить поля

        project = ProjectConfig(name=name, kicad_project=kicad_project,
                                netlist=netlist, output_dir=output_dir)
        try:
            if config_path is not None:
                append_project(config_path, project)
            config.projects.append(project)
            if handler() is not None:
                handler().register_project(project)
        except Exception:
            logger.exception("Не удалось сохранить проект %s — файл конфига не тронут", project.name)
            error_var.set("Не удалось сохранить проект в конфиг — см. лог.")
            return

        logger.info("Проект %s добавлен в конфиг и начинает отслеживаться", project.name)
        _refresh_list()
        _reset_to_new_mode()

        # Первичный прогон в отдельном фоне — окно не замораживается.
        def _run_new() -> None:
            try:
                run_project(project, config)
            except FileNotFoundError as e:
                logger.error("Первичный прогон пропущен для проекта %s: %s", project.name, e)
            except Exception:
                logger.exception("Первичный прогон упал для проекта %s", project.name)

        threading.Thread(target=_run_new, daemon=True).start()

    def on_edit() -> None:
        name = _selected_name()
        project = _find_project(name) if name else None
        if project is not None:
            _enter_editing_mode(project)

    def on_save_edit() -> None:
        old_name = editing_original_name[0]
        if old_name is None:
            return
        name = field_vars["name"].get().strip()
        kicad_project = field_vars["kicad_project"].get().strip()
        netlist = field_vars["netlist"].get().strip()
        output_dir = field_vars["output_dir"].get().strip()

        # Дефолты — те же, что в config.py::load_config.
        if not name and netlist:
            name = Path(netlist).stem
        if not output_dir and netlist:
            output_dir = str(Path(netlist).parent / "out")

        # others уже исключает старую запись, поэтому переименование в своё же
        # имя не посчитается дублем.
        others = [p for p in config.projects if p.name != old_name]
        errors = validate_new_project(name, kicad_project, netlist, others)
        if errors:
            error_var.set("\n".join(errors))
            return

        project = ProjectConfig(name=name, kicad_project=kicad_project,
                                netlist=netlist, output_dir=output_dir)
        try:
            if config_path is not None:
                update_project(config_path, old_name, project)
            config.projects[:] = [project if p.name == old_name else p
                                  for p in config.projects]
            if handler() is not None:
                handler().update_project(old_name, project)
        except Exception:
            logger.exception("Не удалось сохранить изменения проекта %s", old_name)
            error_var.set("Не удалось сохранить изменения — см. лог.")
            return

        logger.info("Проект %s обновлён (было «%s»)", project.name, old_name)
        editing_original_name[0] = None
        _refresh_list()
        _select_item_by_name(project.name)
        _enter_selected_mode(project)

    def on_cancel_edit() -> None:
        old_name = editing_original_name[0]
        editing_original_name[0] = None
        project = _find_project(old_name) if old_name else None
        if project is None:
            _reset_to_new_mode()
        else:
            _enter_selected_mode(project)  # перечитывает из config.projects, не из полей

    def on_delete() -> None:
        name = _selected_name()
        if name is None:
            return
        project = _find_project(name)
        out_dir = project.output_dir if project else ""
        if not messagebox.askyesno(
            "Удалить проект",
            f"Удалить проект «{name}» из конфига и из слежения?\n\n"
            f"Файлы в папке вывода ({out_dir}) НЕ удаляются — "
            f"удаляется только запись в конфиге.",
            parent=root,
        ):
            return
        try:
            if config_path is not None:
                remove_project(config_path, name)
            config.projects[:] = [p for p in config.projects if p.name != name]
            if handler() is not None:
                handler().unregister_project(name)
        except ValueError as e:
            logger.error("%s", e)
            error_var.set(str(e))
            return
        except Exception:
            logger.exception("Не удалось удалить проект %s — файл конфига не тронут", name)
            error_var.set("Не удалось удалить проект из конфига — см. лог.")
            return

        logger.info("Проект %s удалён из конфига и из слежения", name)
        _refresh_list()
        _reset_to_new_mode()

    def on_freeze() -> None:
        name = _selected_name()
        h = handler()
        if name is None or h is None:
            return
        frozen = h.is_frozen(name)
        h.set_frozen(name, not frozen)
        sel = tree.selection()
        if sel:
            status = "⏸ заморожен" if not frozen else "▶ активен"
            tree.item(sel[0], values=(status,))
        freeze_btn.config(text="Разморозить" if not frozen else "Заморозить")

    add_btn.config(command=on_add)
    edit_btn.config(command=on_edit)
    save_btn.config(command=on_save_edit)
    cancel_btn.config(command=on_cancel_edit)
    del_btn.config(command=on_delete)
    freeze_btn.config(command=on_freeze)

    _refresh_list()
    _reset_to_new_mode()
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

    config_path и watch_handle нужны пункту «Настройки...»: первый — чтобы
    дописывать/удалять проекты в YAML (с сохранением комментариев), второй —
    чтобы заводить их в живом наблюдателе без перезапуска приложения.
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

    def on_settings(icon, item):
        # pystray.Icon.run() занимает главный поток, Tk требует свой mainloop —
        # поэтому окно открываем в отдельном потоке со своим tk.Tk().
        threading.Thread(
            target=_show_settings_window,
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
        pystray.MenuItem("Настройки...", on_settings),
        pystray.MenuItem("Выход", on_exit),
    )
    return pystray.Icon("kicad-net-exporter", _make_icon_image(), "KiCad Net Exporter", menu)


def run_tray(config: AppConfig, stop_flag: threading.Event, paused: threading.Event, log_path: Path | None) -> None:
    build_icon(config, stop_flag, paused, log_path).run()
