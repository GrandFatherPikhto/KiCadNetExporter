"""Тесты точки входа: чистое решение «поднимать ли трей» и smoke-прогон CLI
(main() с --once на синтетическом проекте)."""
from __future__ import annotations

import logging
import sys

import pytest

from netexp.app.main import main, should_run_tray

from . import data as T


@pytest.fixture
def clean_root_logger():
    """main() вызывает setup_logging и перенастраивает корневой логгер —
    восстанавливаем его, чтобы не влиять на соседние тесты."""
    root = logging.getLogger()
    saved = list(root.handlers)
    saved_level = root.level
    yield root
    root.handlers[:] = saved
    root.setLevel(saved_level)


class _FakeConfig:
    def __init__(self, tray_enabled: bool):
        self.tray = type("_Tray", (), {"enabled": tray_enabled})()


class TestShouldRunTray:
    def test_win32_enabled_raises_tray(self):
        assert should_run_tray(_FakeConfig(True), no_tray=False, platform="win32") is True

    def test_win32_disabled_no_tray(self):
        assert should_run_tray(_FakeConfig(False), no_tray=False, platform="win32") is False

    def test_no_tray_flag_wins_on_win32(self):
        assert should_run_tray(_FakeConfig(True), no_tray=True, platform="win32") is False

    def test_linux_never_raises_tray(self):
        assert should_run_tray(_FakeConfig(True), no_tray=False, platform="linux") is False

    def test_darwin_never_raises_tray(self):
        assert should_run_tray(_FakeConfig(True), no_tray=False, platform="darwin") is False

    def test_default_platform_uses_sys_platform(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert should_run_tray(_FakeConfig(True), no_tray=False) is True
        monkeypatch.setattr(sys, "platform", "linux")
        assert should_run_tray(_FakeConfig(True), no_tray=False) is False


class TestCliOnce:
    def test_once_generates_reports(self, tmp_path, monkeypatch, clean_root_logger):
        net = tmp_path / "demo.net"
        pro = tmp_path / "demo.kicad_pro"
        net.write_text(T.SAMPLE_NET, encoding="utf-8")
        pro.write_text(T.SAMPLE_KICAD_PRO, encoding="utf-8")
        out = tmp_path / "out"
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "projects:\n"
            "  - name: demo\n"
            f"    kicad_project: '{pro}'\n"
            f"    netlist: '{net}'\n"
            f"    output_dir: '{out}'\n"
            "output:\n"
            "  formats: [txt, json]\n"
            "  diff: true\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["netexp", str(cfg), "--once"])

        main()

        assert out.is_dir()
        assert (out / "demo_net.txt").exists()
        assert (out / "demo_bom.json").exists()

    def test_once_missing_netlist_does_not_raise(self, tmp_path, monkeypatch, clean_root_logger):
        pro = tmp_path / "demo.kicad_pro"
        pro.write_text(T.SAMPLE_KICAD_PRO, encoding="utf-8")
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "projects:\n"
            "  - name: demo\n"
            f"    kicad_project: '{pro}'\n"
            f"    netlist: '{tmp_path / 'missing.net'}'\n"
            f"    output_dir: '{tmp_path / 'out'}'\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["netexp", str(cfg), "--once"])

        # --once ловит FileNotFoundError по каждому проекту и просто логирует
        main()
