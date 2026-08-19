"""Тесты загрузки YAML-конфига: load_config."""
from __future__ import annotations

import pytest

from netexp.app.config import load_config

VALID_YAML = """\
projects:
  - name: demo
    kicad_project: "./demo.kicad_pro"
    netlist: "./demo.net"
    output_dir: "./out"
  - kicad_project: "/abs/p.kicad_pro"
    netlist: "/abs/p.net"

output:
  formats: [txt, json, md]
  raw_txt_copy: true
  diff: false

classification:
  power_patterns: ["(?i)^GND$"]
  suspicious_patterns: ["(?i)clk"]

watch:
  enabled: false
  debounce_sec: 2.0
  settle_delay_sec: 0.5

logging:
  level: DEBUG
  file: "logs/app.log"
  max_bytes: 2048
  backup_count: 5
  console: false

tray:
  enabled: false
"""


def _write(tmp_path, content: str):
    p = tmp_path / "config.yaml"
    p.write_text(content, encoding="utf-8")
    return p


class TestLoadConfig:
    def test_full_config(self, tmp_path):
        cfg = load_config(_write(tmp_path, VALID_YAML))
        assert len(cfg.projects) == 2

        p1 = cfg.projects[0]
        assert p1.name == "demo"
        assert p1.kicad_project == "./demo.kicad_pro"
        assert p1.netlist == "./demo.net"
        assert p1.output_dir == "./out"

        assert cfg.output.formats == ["txt", "json", "md"]
        assert cfg.output.raw_txt_copy is True
        assert cfg.output.diff is False

        assert cfg.classification.power_patterns == ["(?i)^GND$"]
        assert cfg.classification.suspicious_patterns == ["(?i)clk"]

        assert cfg.watch.enabled is False
        assert cfg.watch.debounce_sec == 2.0
        assert cfg.watch.settle_delay_sec == 0.5

        assert cfg.logging.level == "DEBUG"
        assert cfg.logging.file == "logs/app.log"
        assert cfg.logging.max_bytes == 2048
        assert cfg.logging.backup_count == 5
        assert cfg.logging.console is False

        assert cfg.tray.enabled is False

    def test_defaults_for_missing_sections(self, tmp_path):
        cfg = load_config(_write(tmp_path, (
            "projects:\n"
            "  - kicad_project: a.kicad_pro\n"
            "    netlist: a.net\n"
            "  - kicad_project: b.kicad_pro\n"
            "    netlist: b.net\n"
        )))
        # имя по умолчанию — stem netlist
        assert cfg.projects[0].name == "a"
        assert cfg.projects[1].name == "b"
        # output_dir по умолчанию — <каталог netlist>/out
        from pathlib import Path

        assert Path(cfg.projects[0].output_dir) == Path("out")
        # секции по умолчанию
        assert cfg.output.formats == ["txt", "json"]
        assert cfg.output.diff is True
        assert cfg.watch.enabled is True
        assert cfg.tray.enabled is True

    def test_minimal_project_requires_required_keys(self, tmp_path):
        # kicad_project/netlist обязательны
        with pytest.raises(KeyError):
            load_config(_write(tmp_path, "projects:\n  - name: x\n"))

    def test_no_projects_raises(self, tmp_path):
        with pytest.raises(ValueError, match="projects"):
            load_config(_write(tmp_path, "output:\n  formats: [txt]\n"))

    def test_empty_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="projects"):
            load_config(_write(tmp_path, ""))

    def test_default_power_patterns(self, tmp_path):
        cfg = load_config(_write(tmp_path, (
            "projects:\n  - kicad_project: a.kicad_pro\n    netlist: a.net\n"
        )))
        assert cfg.classification.power_patterns  # не пусто по умолчанию
