"""Тесты KiCadNetParser — разбор .net (sexp) в core-модель."""
from __future__ import annotations

import pytest

from netexp.core.models import NetKind
from netexp.infra.parsers.net_parser import KiCadNetParser

from . import data as T


def _write(tmp_path, content: str, name: str = "probe.net"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


class TestKiCadNetParser:
    def test_parse_components(self, demo_doc):
        by_ref = {c.ref: c for c in demo_doc.components}
        assert set(by_ref) == {"R1", "U1", "U2", "C1"}
        # U1A/U1B -> U1 (многосекционный схлопывается, первая секция выигрывает)
        assert by_ref["U1"].value == "STM32F103"
        assert by_ref["U1"].footprint == "LQFP-48"
        # footprint без префикса библиотеки
        assert by_ref["R1"].footprint == "R_0603"
        # пустой footprint -> missing
        assert by_ref["C1"].missing_footprint is True
        assert by_ref["C1"].footprint == "~"
        assert by_ref["R1"].missing_footprint is False

    def test_parse_nets(self, demo_doc):
        by_name = {n.name: n for n in demo_doc.nets}
        assert set(by_name) == {"+5V", "GND", "/Power/Filter/+3V3",
                                "/Power/Filter/CLK_OUT",
                                "unconnected-(U1-Pad14)", "USB_DP2"}
        # пины собраны, U1A/U1B -> U1
        gnd = by_name["GND"]
        assert gnd.sheet_path == []
        assert len(gnd.pins) == 3
        refs = {p.component_ref for p in gnd.pins}
        assert refs == {"R1", "U1", "U2"}

        hier = by_name["/Power/Filter/+3V3"]
        assert hier.sheet_path == ["Power", "Filter"]
        assert hier.leaf == "+3V3"

    def test_parse_metadata(self, demo_doc):
        assert demo_doc.metadata["source_sheet"] == "demo.sch"
        assert demo_doc.metadata["tool"] == "Eeschema"
        assert demo_doc.metadata["date"] == "2026-07-11"

    def test_parse_source_file_name(self, sample_net_path):
        parser = KiCadNetParser()
        doc = parser.parse(str(sample_net_path))
        assert doc.source_file_name == "demo.net"

    def test_empty_netlist(self, tmp_path):
        path = _write(tmp_path, T.EMPTY_NET)
        doc = KiCadNetParser().parse(path)
        assert doc.components == []
        assert doc.nets == []

    def test_unknown_sections_are_ignored(self, tmp_path):
        # KiCad 10 добавляет (sheet ...)/(title_block ...) в design — парсер
        # должен их молча пропускать, а не падать.
        content = """\
(export (version "E")
  (design
    (source "s.sch")
    (tool "Eeschema")
    (sheet (path "/") (tstamps "/")
      (title_block (title "T") (company "X"))))
  (components)
  (nets)
  (variants))
"""
        doc = KiCadNetParser().parse(_write(tmp_path, content))
        assert doc.metadata["source_sheet"] == "s.sch"
        assert doc.components == []
        assert doc.nets == []

    def test_pins_dedup(self, tmp_path):
        content = """\
(export (version "E")
  (components (comp (ref "R1") (value "1k") (footprint "R")))
  (nets
    (net (name "X")
      (node (ref "R1") (pin "1"))
      (node (ref "R1") (pin "1")))))
"""
        doc = KiCadNetParser().parse(_write(tmp_path, content))
        assert len(doc.nets) == 1
        assert len(doc.nets[0].pins) == 1  # дубликат (ref, pin) отброшен

    def test_empty_or_whitespace_file_raises(self, tmp_path):
        # Парсер не должен молча вернуть пустую модель на пустом файле —
        # retry исчерпает попытки и пробросит ошибку.
        path = _write(tmp_path, "   \n  \n")
        with pytest.raises(Exception):
            KiCadNetParser().parse(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            KiCadNetParser().parse(str(tmp_path / "nope.net"))
