"""Тесты оркестратора run_project: разбор -> классификация -> генерация."""
from __future__ import annotations

import pytest

from netexp.app.config import (
    AppConfig,
    ClassificationConfig,
    LoggingConfig,
    OutputConfig,
    ProjectConfig,
    TrayConfig,
    WatchConfig,
)
from netexp.app.pipeline import run_project

from . import data as T


def _write(tmp_path):
    net = tmp_path / "demo.net"
    pro = tmp_path / "demo.kicad_pro"
    net.write_text(T.SAMPLE_NET, encoding="utf-8")
    pro.write_text(T.SAMPLE_KICAD_PRO, encoding="utf-8")
    return net, pro


def _config(net_path, pro_path, out_dir, **kwargs) -> AppConfig:
    project = ProjectConfig(
        name="demo",
        kicad_project=str(pro_path),
        netlist=str(net_path),
        output_dir=str(out_dir),
    )
    output = OutputConfig(formats=kwargs.pop("formats", ["txt", "json"]),
                          raw_txt_copy=kwargs.pop("raw_txt_copy", False),
                          diff=kwargs.pop("diff", True))
    return AppConfig(
        projects=[project],
        output=output,
        classification=ClassificationConfig(),
        watch=WatchConfig(enabled=False),
        logging=LoggingConfig(console=False),
        tray=TrayConfig(enabled=False),
    )


class TestRunProject:
    def test_full_run(self, tmp_path):
        net, pro = _write(tmp_path)
        out_dir = tmp_path / "out"
        cfg = _config(net, pro, out_dir)
        written = run_project(cfg.projects[0], cfg)

        assert out_dir.is_dir()
        assert (out_dir / "demo_net.txt").exists()
        assert (out_dir / "demo_net.json").exists()
        assert (out_dir / "demo_bom.txt").exists()
        assert (out_dir / "demo_power.txt").exists()
        assert (out_dir / "demo_audit.txt").exists()
        assert (out_dir / "demo_unconnected.txt").exists()
        assert (out_dir / "demo_diff.txt").exists()
        assert (out_dir / ".snapshot_demo.json").exists()
        assert len(written) >= 8

    def test_raw_txt_copy(self, tmp_path):
        net, pro = _write(tmp_path)
        out_dir = tmp_path / "out"
        cfg = _config(net, pro, out_dir, raw_txt_copy=True)
        run_project(cfg.projects[0], cfg)
        assert (out_dir / "demo.txt").exists()
        assert (out_dir / "demo.txt").read_text(encoding="utf-8") == T.SAMPLE_NET

    def test_formats_honored(self, tmp_path):
        net, pro = _write(tmp_path)
        out_dir = tmp_path / "out"
        cfg = _config(net, pro, out_dir, formats=["md"])
        run_project(cfg.projects[0], cfg)
        assert (out_dir / "demo_net.md").exists()
        assert not (out_dir / "demo_net.txt").exists()
        assert not (out_dir / "demo_net.json").exists()

    def test_diff_disabled_skips_diff(self, tmp_path):
        net, pro = _write(tmp_path)
        out_dir = tmp_path / "out"
        cfg = _config(net, pro, out_dir, diff=False)
        run_project(cfg.projects[0], cfg)
        assert not (out_dir / "demo_diff.txt").exists()
        assert not (out_dir / ".snapshot_demo.json").exists()

    def test_missing_netlist_raises(self, tmp_path):
        pro = tmp_path / "demo.kicad_pro"
        pro.write_text(T.SAMPLE_KICAD_PRO, encoding="utf-8")
        cfg = _config(tmp_path / "missing.net", pro, tmp_path / "out")
        with pytest.raises(FileNotFoundError, match="нетлиста"):
            run_project(cfg.projects[0], cfg)

    def test_missing_project_file_raises(self, tmp_path):
        net = tmp_path / "demo.net"
        net.write_text(T.SAMPLE_NET, encoding="utf-8")
        cfg = _config(net, tmp_path / "missing.kicad_pro", tmp_path / "out")
        with pytest.raises(FileNotFoundError, match="проекта"):
            run_project(cfg.projects[0], cfg)
