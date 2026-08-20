"""Тесты вотчера: _TrackedFileHandler (debounce, пауза, stale-уведомления,
регистрация нового проекта без перезапуска)."""
from __future__ import annotations

import os
import threading
import time as _time
from pathlib import Path

from watchdog.events import FileModifiedEvent

from netexp.app.config import (
    AppConfig,
    ClassificationConfig,
    LoggingConfig,
    OutputConfig,
    ProjectConfig,
    TrayConfig,
    WatchConfig,
)
from netexp.app import watcher as watcher_mod
from netexp.app.watcher import _TrackedFileHandler

from . import data as T


def _make_config(tmp_path: Path, debounce: float = 1.0) -> tuple[AppConfig, ProjectConfig]:
    net = tmp_path / "demo.net"
    pro = tmp_path / "demo.kicad_pro"
    net.write_text(T.SAMPLE_NET, encoding="utf-8")
    pro.write_text(T.SAMPLE_KICAD_PRO, encoding="utf-8")
    project = ProjectConfig(
        name="demo",
        kicad_project=str(pro),
        netlist=str(net),
        output_dir=str(tmp_path / "out"),
    )
    config = AppConfig(
        projects=[project],
        output=OutputConfig(),
        classification=ClassificationConfig(),
        watch=WatchConfig(enabled=True, debounce_sec=debounce, settle_delay_sec=0),
        logging=LoggingConfig(console=False),
        tray=TrayConfig(enabled=False),
    )
    return config, project


def _handler(config: AppConfig, paused: threading.Event | None = None, on_stale=None):
    return _TrackedFileHandler(config, paused or threading.Event(), on_stale=on_stale)


class TestTrackedFileHandler:
    def test_init_builds_watch_map(self, tmp_path):
        config, project = _make_config(tmp_path)
        handler = _handler(config)
        assert len(handler.watch_map) == 2  # .net и .kicad_pro

    def test_init_skips_missing_files(self, tmp_path):
        config, project = _make_config(tmp_path)
        config.projects[0].netlist = str(tmp_path / "nope.net")
        handler = _handler(config)
        assert len(handler.watch_map) == 1  # только существующий .kicad_pro

    def test_init_tracks_schematics(self, tmp_path):
        config, project = _make_config(tmp_path)
        sch = tmp_path / "demo.kicad_sch"
        sch.write_text("(kicad_sch)", encoding="utf-8")
        handler = _handler(config)
        assert len(handler.sch_watch_map) == 1
        assert Path(next(iter(handler.sch_watch_map))).name == "demo.kicad_sch"

    def test_modified_net_triggers_pipeline(self, tmp_path, monkeypatch):
        config, project = _make_config(tmp_path)
        calls = []
        monkeypatch.setattr(watcher_mod, "run_project",
                            lambda proj, cfg: calls.append((proj.name, cfg)))
        handler = _handler(config)
        handler.on_modified(FileModifiedEvent(str(tmp_path / "demo.net")))
        assert len(calls) == 1
        assert calls[0][0] == "demo"

    def test_unknown_path_ignored(self, tmp_path, monkeypatch):
        config, project = _make_config(tmp_path)
        calls = []
        monkeypatch.setattr(watcher_mod, "run_project", lambda *a, **k: calls.append(1))
        handler = _handler(config)
        handler.on_modified(FileModifiedEvent(str(tmp_path / "other.txt")))
        assert calls == []

    def test_paused_ignores_events(self, tmp_path, monkeypatch):
        config, project = _make_config(tmp_path)
        calls = []
        monkeypatch.setattr(watcher_mod, "run_project", lambda *a, **k: calls.append(1))
        paused = threading.Event()
        paused.set()
        handler = _handler(config, paused=paused)
        handler.on_modified(FileModifiedEvent(str(tmp_path / "demo.net")))
        assert calls == []

    def test_debounce_suppresses_repeated_events(self, tmp_path, monkeypatch):
        config, project = _make_config(tmp_path, debounce=100.0)
        calls = []
        monkeypatch.setattr(watcher_mod, "run_project", lambda *a, **k: calls.append(1))
        handler = _handler(config)
        handler.on_modified(FileModifiedEvent(str(tmp_path / "demo.net")))
        handler.on_modified(FileModifiedEvent(str(tmp_path / "demo.net")))
        assert len(calls) == 1

    def test_schematic_event_does_not_run_pipeline(self, tmp_path, monkeypatch):
        config, project = _make_config(tmp_path)
        sch = tmp_path / "demo.kicad_sch"
        sch.write_text("(kicad_sch)", encoding="utf-8")
        calls = []
        monkeypatch.setattr(watcher_mod, "run_project", lambda *a, **k: calls.append(1))
        handler = _handler(config)
        handler.on_modified(FileModifiedEvent(str(sch)))
        assert calls == []
        assert handler._sch_mtime[project.name] > 0


class TestCheckStale:
    def _stale_handler(self, tmp_path, monkeypatch, net_mtime_ago, sch_mtime_ago):
        config, project = _make_config(tmp_path)
        now = _time.time()
        monkeypatch.setattr(watcher_mod.time, "time", lambda: now)
        os.utime(tmp_path / "demo.net", (now - net_mtime_ago, now - net_mtime_ago))
        notifications = []
        handler = _handler(config, on_stale=lambda name, msg: notifications.append((name, msg)))
        handler._sch_mtime[project.name] = now - sch_mtime_ago
        return handler, project, notifications

    def test_stale_notifies_once(self, tmp_path, monkeypatch):
        handler, project, notifications = self._stale_handler(
            tmp_path, monkeypatch, net_mtime_ago=200, sch_mtime_ago=60)
        handler._check_stale(project)
        handler._check_stale(project)  # повторно — не должно быть второго уведомления
        assert len(notifications) == 1
        assert notifications[0][0] == "demo"

    def test_within_grace_no_notify(self, tmp_path, monkeypatch):
        handler, project, notifications = self._stale_handler(
            tmp_path, monkeypatch, net_mtime_ago=200, sch_mtime_ago=10)
        handler._check_stale(project)
        assert notifications == []

    def test_schematic_older_than_netlist_no_notify(self, tmp_path, monkeypatch):
        handler, project, notifications = self._stale_handler(
            tmp_path, monkeypatch, net_mtime_ago=60, sch_mtime_ago=200)
        handler._check_stale(project)
        assert notifications == []

    def test_missing_netlist_no_notify(self, tmp_path, monkeypatch):
        config, project = _make_config(tmp_path)
        now = _time.time()
        monkeypatch.setattr(watcher_mod.time, "time", lambda: now)
        config.projects[0].netlist = str(tmp_path / "missing.net")
        notifications = []
        handler = _handler(config, on_stale=lambda n, m: notifications.append(n))
        handler._sch_mtime[project.name] = now - 60
        handler._check_stale(project)
        assert notifications == []


class TestRegisterProject:
    @staticmethod
    def _new_project(tmp_path) -> tuple[ProjectConfig, Path]:
        new_dir = tmp_path / "other"
        new_dir.mkdir()
        net = new_dir / "b.net"
        pro = new_dir / "b.kicad_pro"
        sch = new_dir / "b.kicad_sch"
        net.write_text(T.SAMPLE_NET, encoding="utf-8")
        pro.write_text(T.SAMPLE_KICAD_PRO, encoding="utf-8")
        sch.write_text("(kicad_sch)", encoding="utf-8")
        return ProjectConfig(name="b", kicad_project=str(pro), netlist=str(net),
                             output_dir=str(new_dir / "out")), new_dir

    def test_register_adds_paths_and_tracks_dir(self, tmp_path):
        config, project = _make_config(tmp_path)
        handler = _handler(config)
        new_project, new_dir = self._new_project(tmp_path)

        handler.register_project(new_project)

        resolved_keys = {k for k in handler.watch_map}
        assert str((new_dir / "b.net").resolve()) in resolved_keys
        assert str((new_dir / "b.kicad_pro").resolve()) in resolved_keys
        assert str((new_dir / "b.kicad_sch").resolve()) in handler.sch_watch_map
        assert str(new_dir.resolve()) in handler.watched_dirs

    def test_register_schedules_directory_in_observer(self, tmp_path):
        config, project = _make_config(tmp_path)
        handler = _handler(config)
        new_project, new_dir = self._new_project(tmp_path)

        scheduled: list[tuple[str, bool]] = []

        class FakeObserver:
            def schedule(self, event_handler, path, recursive=False):
                scheduled.append((str(Path(path).resolve()), recursive))

        handler.observer = FakeObserver()
        handler.register_project(new_project)

        assert str(new_dir.resolve()) in handler.watched_dirs
        assert (str(new_dir.resolve()), False) in scheduled

    def test_register_is_idempotent_for_tracked_dir(self, tmp_path):
        config, project = _make_config(tmp_path)
        handler = _handler(config)
        new_project, new_dir = self._new_project(tmp_path)

        handler.register_project(new_project)
        handler.register_project(new_project)  # повторно — без исключений и дублей

        assert len(handler.watched_dirs) == 1
        assert str(new_dir.resolve()) in handler.watched_dirs

    def test_register_skips_missing_files(self, tmp_path):
        config, project = _make_config(tmp_path)
        handler = _handler(config)
        new_dir = tmp_path / "other"
        new_dir.mkdir()
        new_project = ProjectConfig(
            name="b", kicad_project=str(new_dir / "missing.kicad_pro"),
            netlist=str(new_dir / "missing.net"), output_dir=str(new_dir / "out"),
        )

        handler.register_project(new_project)

        # файлы не существуют — в watch_map ничего не добавляется
        assert str(new_dir.resolve()) not in handler.watched_dirs
        assert all(p.name != "missing.kicad_pro" for p in handler.watch_map.values())
