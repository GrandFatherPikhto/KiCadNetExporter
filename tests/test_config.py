"""Тесты загрузки YAML-конфига: load_config, append/remove/update_project,
validate_new_project."""
from __future__ import annotations

import pytest

from netexp.app.config import (
    ProjectConfig,
    append_project,
    load_config,
    remove_project,
    update_project,
    validate_new_project,
)

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


class TestAppendProject:
    CONFIG_WITH_COMMENTS = """\
# Шапка — комментарий, который нельзя терять.
# Ещё пояснение к проектам.

projects:
  - name: demo
    kicad_project: "./demo.kicad_pro"
    netlist: "./demo.net"
    output_dir: "./out"

output:
  formats: [txt, json]
"""

    def test_comments_survive_and_entry_appended(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG_WITH_COMMENTS, encoding="utf-8")
        append_project(p, ProjectConfig(
            name="newproj", kicad_project="./new.kicad_pro",
            netlist="./new.net", output_dir="./new_out",
        ))

        text = p.read_text(encoding="utf-8")
        assert "# Шапка — комментарий, который нельзя терять." in text
        assert "# Ещё пояснение к проектам." in text
        assert "- name: newproj" in text
        assert "kicad_project: ./new.kicad_pro" in text
        assert "netlist: ./new.net" in text
        assert "output_dir: ./new_out" in text

        # бэкап создан
        assert (tmp_path / "config.yaml.bak").exists()

        # файл после дописывания остаётся валидным для load_config
        cfg = load_config(p)
        assert len(cfg.projects) == 2
        assert cfg.projects[-1].name == "newproj"
        assert cfg.projects[-1].output_dir == "./new_out"

    def test_backup_matches_original(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG_WITH_COMMENTS, encoding="utf-8")
        original = p.read_text(encoding="utf-8")
        append_project(p, ProjectConfig(
            name="x", kicad_project="x.kicad_pro", netlist="x.net", output_dir="x/out",
        ))
        assert (tmp_path / "config.yaml.bak").read_text(encoding="utf-8") == original


class TestValidateNewProject:
    @staticmethod
    def _existing(*names):
        return [ProjectConfig(name=n, kicad_project="x", netlist="x", output_dir="x")
                for n in names]

    @staticmethod
    def _write_pair(tmp_path, stem="a"):
        net = tmp_path / f"{stem}.net"
        pro = tmp_path / f"{stem}.kicad_pro"
        net.write_text("(netlist)", encoding="utf-8")
        pro.write_text("(kicad_pro)", encoding="utf-8")
        return net, pro

    def test_ok(self, tmp_path):
        net, pro = self._write_pair(tmp_path)
        assert validate_new_project("new", str(pro), str(net),
                                    self._existing("demo")) == []

    def test_missing_files(self, tmp_path):
        errors = validate_new_project(
            "new", str(tmp_path / "nope.kicad_pro"), str(tmp_path / "nope.net"),
            self._existing("demo"))
        assert len(errors) == 2
        assert any("kicad_pro" in e for e in errors)
        assert any(".net" in e for e in errors)

    def test_duplicate_name(self, tmp_path):
        net, pro = self._write_pair(tmp_path)
        errors = validate_new_project("dup", str(pro), str(net),
                                      self._existing("demo", "dup"))
        assert any("уже есть" in e for e in errors)

    def test_duplicate_and_missing_files_reported_together(self, tmp_path):
        errors = validate_new_project(
            "demo", str(tmp_path / "no.kicad_pro"), str(tmp_path / "no.net"),
            self._existing("demo"))
        assert len(errors) == 3  # дубликат + оба файла не найдены

    def test_empty_name_is_error(self, tmp_path):
        net, pro = self._write_pair(tmp_path)
        errors = validate_new_project("", str(pro), str(net), self._existing("demo"))
        assert any("имя" in e for e in errors)

    def test_exclude_name_allows_renaming_to_self(self, tmp_path):
        net, pro = self._write_pair(tmp_path)
        # переименование demo -> demo (имя не менялось) с exclude_name не дубль
        assert validate_new_project("demo", str(pro), str(net),
                                    self._existing("demo", "other"),
                                    exclude_name="demo") == []

    def test_exclude_name_still_catches_other_duplicate(self, tmp_path):
        net, pro = self._write_pair(tmp_path)
        # переименование demo -> other (имя занято другим проектом) — ошибка
        errors = validate_new_project("other", str(pro), str(net),
                                      self._existing("demo", "other"),
                                      exclude_name="demo")
        assert any("уже есть" in e for e in errors)


class TestRemoveProject:
    CONFIG_TWO = """\
# Шапка.
projects:
  - name: demo
    kicad_project: "./demo.kicad_pro"
    netlist: "./demo.net"
    output_dir: "./out"
  - name: other
    kicad_project: "./other.kicad_pro"
    netlist: "./other.net"
    output_dir: "./other_out"

output:
  formats: [txt, json]
"""

    def test_removes_only_requested_project(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG_TWO, encoding="utf-8")
        remove_project(p, "demo")

        text = p.read_text(encoding="utf-8")
        assert "- name: demo" not in text
        assert "- name: other" in text
        assert "# Шапка." in text  # комментарий выжил

        cfg = load_config(p)
        assert [pr.name for pr in cfg.projects] == ["other"]

    def test_backup_created(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG_TWO, encoding="utf-8")
        original = p.read_text(encoding="utf-8")
        remove_project(p, "demo")

        bak = tmp_path / "config.yaml.bak"
        assert bak.exists()
        assert bak.read_text(encoding="utf-8") == original

    def test_missing_name_raises_and_config_untouched(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG_TWO, encoding="utf-8")
        original = p.read_text(encoding="utf-8")
        with pytest.raises(ValueError, match="nope"):
            remove_project(p, "nope")
        assert p.read_text(encoding="utf-8") == original
        assert not (tmp_path / "config.yaml.bak").exists()


class TestUpdateProject:
    CONFIG = TestRemoveProject.CONFIG_TWO

    def test_rename(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG, encoding="utf-8")
        update_project(p, "demo", ProjectConfig(
            name="demo-renamed", kicad_project="./new.kicad_pro",
            netlist="./new.net", output_dir="./new_out",
        ))

        text = p.read_text(encoding="utf-8")
        assert "- name: demo-renamed" in text
        assert "- name: other" in text  # соседняя запись не тронута
        assert "# Шапка." in text       # комментарий выжил

        cfg = load_config(p)
        # единственный источник истины — перечитывание конфига
        assert [pr.name for pr in cfg.projects] == ["demo-renamed", "other"]

    def test_edit_without_rename(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG, encoding="utf-8")
        update_project(p, "other", ProjectConfig(
            name="other", kicad_project="./other2.kicad_pro",
            netlist="./other2.net", output_dir="./other2_out",
        ))
        cfg = load_config(p)
        assert cfg.projects[1].kicad_project == "./other2.kicad_pro"
        assert cfg.projects[1].netlist == "./other2.net"
        assert cfg.projects[1].output_dir == "./other2_out"

    def test_backup_created(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG, encoding="utf-8")
        original = p.read_text(encoding="utf-8")
        update_project(p, "demo", ProjectConfig(
            name="demo-x", kicad_project="x.kicad_pro", netlist="x.net", output_dir="x/out",
        ))
        bak = tmp_path / "config.yaml.bak"
        assert bak.exists()
        assert bak.read_text(encoding="utf-8") == original

    def test_missing_old_name_raises_and_config_untouched(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(self.CONFIG, encoding="utf-8")
        original = p.read_text(encoding="utf-8")
        with pytest.raises(ValueError, match="nope"):
            update_project(p, "nope", ProjectConfig(
                name="x", kicad_project="x", netlist="x", output_dir="x",
            ))
        assert p.read_text(encoding="utf-8") == original
        assert not (tmp_path / "config.yaml.bak").exists()
