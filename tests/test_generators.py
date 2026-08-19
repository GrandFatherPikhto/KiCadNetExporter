"""Тесты всех генераторов отчётов (net/bom/unconnected/power/audit/patterns/diff)."""
from __future__ import annotations

import json

import pytest

from netexp.core.models import Component, Net, NetClassDef, NetKind, NetlistDocument, PinConnection
from netexp.infra.generators import (
    audit_generator,
    bom_generator,
    diff_generator,
    net_generator,
    patterns_generator,
    power_generator,
    unconnected_generator,
)

from .conftest import make_context, make_doc


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# net_generator
# ---------------------------------------------------------------------------
class TestNetGenerator:
    def test_generate_writes_files(self, ctx):
        written = net_generator.generate(ctx)
        names = {p.name for p in written}
        assert {"demo_net.txt", "demo_net.json"} <= names
        assert (ctx.out_dir / "demo_net.txt").exists()

    def test_text_header_and_counts(self, ctx):
        net_generator.generate(ctx)
        text = (ctx.out_dir / "demo_net.txt").read_text(encoding="utf-8")
        assert "# demo — нетлист (упрощённый)" in text
        assert "Цепей всего: 6 (без unconnected: 5)" in text
        assert "## / (корень)" in text
        assert "## /Power/Filter" in text

    def test_text_includes_netclass_and_pins(self, ctx):
        net_generator.generate(ctx)
        text = (ctx.out_dir / "demo_net.txt").read_text(encoding="utf-8")
        assert "  +5V  [Power]" in text
        assert "    R1 (10k) -> пины: 1" in text
        assert "    U1 (STM32F103) -> пины: 12" in text
        # иерархическая цепь в своей группе, с полным именем
        assert "  /Power/Filter/+3V3  [Default]" in text
        # предупреждение о компоненте без footprint
        assert "[!! НЕТ ФУТПРИНТА !!]" in text

    def test_text_excludes_unconnected(self, ctx):
        net_generator.generate(ctx)
        text = (ctx.out_dir / "demo_net.txt").read_text(encoding="utf-8")
        # сама unconnected-цепь не должна присутствовать в списке (заголовок
        # со словом «unconnected» есть, но конкретной цепи быть не должно)
        assert "unconnected-(U1-Pad14)" not in text

    def test_json_structure(self, ctx):
        net_generator.generate(ctx)
        data = _read_json(ctx.out_dir / "demo_net.json")
        assert data["source_file"] == "demo.net"
        assert data["total_nets"] == 6
        assert data["connected_nets"] == 5
        names = [n["name"] for n in data["nets"]]
        assert names == ["+5V", "/Power/Filter/+3V3", "/Power/Filter/CLK_OUT", "GND", "USB_DP2"]
        first = data["nets"][0]
        assert first["netclass"] == "Power"
        assert first["sheet_path"] == []
        assert first["nodes"][0]["ref"] == "R1"

    def test_md_format_also_written(self, ctx):
        ctx.formats = {"txt", "md"}
        written = net_generator.generate(ctx)
        assert any(p.name == "demo_net.md" for p in written)


# ---------------------------------------------------------------------------
# bom_generator
# ---------------------------------------------------------------------------
class TestBomGenerator:
    def test_writes_files(self, ctx):
        written = bom_generator.generate(ctx)
        assert {p.name for p in written} == {"demo_bom.txt", "demo_bom.json"}

    def test_text_mentions_missing_footprint(self, ctx):
        bom_generator.generate(ctx)
        text = (ctx.out_dir / "demo_bom.txt").read_text(encoding="utf-8")
        assert "=== BOM (список компонентов) для demo.net ===" in text
        assert "!!! ВНИМАНИЕ: компоненты без посадочного места (footprint) !!!" in text
        assert "  - C1 (номинал: 100n)" in text

    def test_json_sorted_by_ref(self, ctx):
        bom_generator.generate(ctx)
        data = _read_json(ctx.out_dir / "demo_bom.json")
        assert [c["ref"] for c in data] == ["C1", "R1", "U1", "U2"]
        c1 = next(c for c in data if c["ref"] == "C1")
        assert c1["missing_footprint"] is True
        assert c1["footprint"] == "~"


# ---------------------------------------------------------------------------
# unconnected_generator
# ---------------------------------------------------------------------------
class TestUnconnectedGenerator:
    def test_only_unconnected_nets(self, ctx):
        unconnected_generator.generate(ctx)
        data = _read_json(ctx.out_dir / "demo_unconnected.json")
        assert [n["name"] for n in data] == ["unconnected-(U1-Pad14)"]
        assert data[0]["pins"] == ["U1.14"]

    def test_text(self, ctx):
        unconnected_generator.generate(ctx)
        text = (ctx.out_dir / "demo_unconnected.txt").read_text(encoding="utf-8")
        assert "=== Unconnected / no-connect цепи (1) ===" in text
        assert "  unconnected-(U1-Pad14) -> U1.14" in text


# ---------------------------------------------------------------------------
# power_generator
# ---------------------------------------------------------------------------
class TestPowerGenerator:
    def test_only_power_nets(self, ctx):
        power_generator.generate(ctx)
        data = _read_json(ctx.out_dir / "demo_power.json")
        assert [n["name"] for n in data] == ["+5V", "GND"]
        assert data[0]["netclass"] == "Power"

    def test_text(self, ctx):
        power_generator.generate(ctx)
        text = (ctx.out_dir / "demo_power.txt").read_text(encoding="utf-8")
        assert "=== Цепи питания (POWER) (2) ===" in text
        assert "  +5V [Power] -> R1.1, U1.12" in text
        assert "  GND [Power] -> U2.1, R1.2, U1.13" in text


# ---------------------------------------------------------------------------
# audit_generator
# ---------------------------------------------------------------------------
class TestAuditGenerator:
    def test_text_counts_and_default(self, ctx):
        audit_generator.generate(ctx)
        text = (ctx.out_dir / "demo_audit.txt").read_text(encoding="utf-8")
        assert "Цепей (без unconnected): 5" in text
        assert "[Default] 1 цепей — мимо всех паттернов:" in text
        assert "    /Power/Filter/+3V3" in text

    def test_text_suspicious_and_rules(self, ctx):
        audit_generator.generate(ctx)
        text = (ctx.out_dir / "demo_audit.txt").read_text(encoding="utf-8")
        assert "!! Подозрительные в Default (1)" in text
        # правила трассировки Power видны в сводке
        assert "track=0.50 clr=0.20 via=0.80/0.40mm" in text

    def test_json_structure(self, ctx):
        audit_generator.generate(ctx)
        data = _read_json(ctx.out_dir / "demo_audit.json")
        assert data["total_considered"] == 5
        assert data["default_unmatched"] == ["/Power/Filter/+3V3"]
        assert data["suspicious_default"] == ["/Power/Filter/+3V3"]
        # by_class только для объявленных классов
        assert data["by_class"]["Power"] == ["+5V", "GND"]
        assert data["by_class"]["Clock"] == ["/Power/Filter/CLK_OUT"]
        # классы отсортированы по priority
        prios = [c["priority"] for c in data["classes"]]
        assert prios == sorted(prios)

    def test_overlaps_rendered(self, ctx):
        ctx.overlaps = [("DUAL", ["Power", "Clock"])]
        audit_generator.generate(ctx)
        text = (ctx.out_dir / "demo_audit.txt").read_text(encoding="utf-8")
        assert "!! Цепи, попавшие в несколько классов (победил меньший priority):" in text
        assert "   DUAL -> ['Power', 'Clock']" in text


# ---------------------------------------------------------------------------
# patterns_generator
# ---------------------------------------------------------------------------
class TestPatternsGenerator:
    def test_text_statuses(self, ctx):
        patterns_generator.generate(ctx)
        text = (ctx.out_dir / "demo_patterns.txt").read_text(encoding="utf-8")
        assert "=== Netclass-паттерны из .kicad_pro ===" in text
        assert "(OK)" in text
        assert "(ОШИБКА)" in text

    def test_text_warnings(self, ctx):
        patterns_generator.generate(ctx)
        text = (ctx.out_dir / "demo_patterns.txt").read_text(encoding="utf-8")
        assert "бэкслеш" in text          # Clock
        assert "не объявлен" in text      # Ghost
        assert "не компилируется" in text  # Broken

    def test_json(self, ctx):
        patterns_generator.generate(ctx)
        data = _read_json(ctx.out_dir / "demo_patterns.json")
        by_cls = {p["netclass"]: p for p in data}
        assert by_cls["Clock"]["pattern"] == "CLK.*"
        assert by_cls["Broken"]["compiled_ok"] is False


# ---------------------------------------------------------------------------
# diff_generator
# ---------------------------------------------------------------------------
class TestDiffGenerator:
    def test_first_run_says_no_snapshot(self, ctx):
        written = diff_generator.generate(ctx)
        assert {p.name for p in written} == {"demo_diff.txt", "demo_diff.json"}
        text = (ctx.out_dir / "demo_diff.txt").read_text(encoding="utf-8")
        assert "=== Diff с прошлого прогона: demo ===" in text
        assert "(снапшота ещё не было — это первый прогон)" in text
        # снапшот записан
        assert (ctx.out_dir / ".snapshot_demo.json").exists()

    def test_no_changes(self, ctx):
        diff_generator.generate(ctx)  # первый прогон создаёт снапшот
        written = diff_generator.generate(ctx)  # второй — без изменений
        text = (ctx.out_dir / "demo_diff.txt").read_text(encoding="utf-8")
        assert "Изменений нет." in text

    def test_changes_reported(self, ctx):
        diff_generator.generate(ctx)
        # меняем состояние: добавляем цепь, убираем другую, меняем netclass
        ctx.doc.nets.append(Net(name="NEW_NET", netclass="Clock", kind=NetKind.NORMAL))
        ctx.doc.nets = [n for n in ctx.doc.nets if n.name != "GND"]
        for n in ctx.doc.nets:
            if n.name == "+5V":
                n.netclass = "Clock"

        diff_generator.generate(ctx)
        text = (ctx.out_dir / "demo_diff.txt").read_text(encoding="utf-8")
        assert "+ Новые цепи (1):" in text
        assert "    + NEW_NET" in text
        assert "- Пропавшие цепи (1):" in text
        assert "    - GND" in text
        assert "~ Сменили netclass (1):" in text
        assert "    ~ +5V: Power -> Clock" in text

    def test_snapshot_updated(self, ctx):
        diff_generator.generate(ctx)
        data = _read_json(ctx.out_dir / ".snapshot_demo.json")
        assert "NEW_NET" not in data["nets"]
        ctx.doc.nets.append(Net(name="NEW_NET", netclass="Clock", kind=NetKind.NORMAL))
        diff_generator.generate(ctx)
        data = _read_json(ctx.out_dir / ".snapshot_demo.json")
        assert data["nets"]["NEW_NET"] == "Clock"

    def test_disabled_returns_empty(self, ctx):
        ctx.diff_enabled = False
        assert diff_generator.generate(ctx) == []
        assert not (ctx.out_dir / ".snapshot_demo.json").exists()

    def test_no_snapshot_path_returns_empty(self, ctx):
        ctx.snapshot_path = None
        assert diff_generator.generate(ctx) == []

    def test_corrupt_snapshot_treated_as_missing(self, ctx):
        (ctx.out_dir / ".snapshot_demo.json").write_text("{broken", encoding="utf-8")
        written = diff_generator.generate(ctx)
        text = (ctx.out_dir / "demo_diff.txt").read_text(encoding="utf-8")
        assert "первый прогон" in text
        assert written  # файлы всё равно записаны


# ---------------------------------------------------------------------------
# параметризованные «пустые» сценарии
# ---------------------------------------------------------------------------
class TestGeneratorsOnEmptyDoc:
    @pytest.mark.parametrize(
        "gen,name",
        [
            (net_generator, "demo_net"),
            (bom_generator, "demo_bom"),
            (unconnected_generator, "demo_unconnected"),
            (power_generator, "demo_power"),
            (audit_generator, "demo_audit"),
            (patterns_generator, "demo_patterns"),
        ],
    )
    def test_generate_empty_doc(self, gen, name, tmp_path):
        ctx = make_context(make_doc(nets=[], components=[]), out_dir=tmp_path)
        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        written = gen.generate(ctx)
        assert any(p.name == f"{name}.txt" for p in written)
