"""Тесты общих helper'ов генераторов: _common.py."""
from __future__ import annotations

import json

from netexp.infra.generators._common import (
    pin_sort_key,
    ref_sort_key,
    write_json_output,
    write_text_outputs,
)


class TestRefSortKey:
    def test_letters_then_number(self):
        # числовое сравнение: R2 < R10
        assert ref_sort_key("R2") < ref_sort_key("R10")
        assert ref_sort_key("C1") < ref_sort_key("U1")

    def test_digitless_ref(self):
        assert ref_sort_key("R") == ("R", 0)
        # "net-1" матчится как буквы "net" без цифр -> число 0
        assert ref_sort_key("net-1") == ("net", 0)

    def test_sorting_components(self):
        refs = ["U1", "R10", "R2", "C1"]
        assert sorted(refs, key=ref_sort_key) == ["C1", "R2", "R10", "U1"]


class TestPinSortKey:
    def test_numeric_first(self):
        assert pin_sort_key("2") < pin_sort_key("10")
        assert pin_sort_key("1") < pin_sort_key("A1")

    def test_alpha_after_numeric(self):
        assert pin_sort_key("10") < pin_sort_key("A1")


class TestWriteTextOutputs:
    def test_txt_and_md(self, tmp_path):
        written = write_text_outputs(tmp_path, "demo", "net", "hello", {"txt", "md"})
        assert set(p.name for p in written) == {"demo_net.txt", "demo_net.md"}
        assert (tmp_path / "demo_net.txt").read_text(encoding="utf-8") == "hello"

    def test_txt_only(self, tmp_path):
        written = write_text_outputs(tmp_path, "demo", "net", "x", {"txt"})
        assert [p.name for p in written] == ["demo_net.txt"]
        assert not (tmp_path / "demo_net.md").exists()

    def test_empty_formats(self, tmp_path):
        assert write_text_outputs(tmp_path, "d", "net", "x", set()) == []


class TestWriteJsonOutput:
    def test_writes_json(self, tmp_path):
        written = write_json_output(tmp_path, "demo", "net", {"a": [1, 2]}, {"json"})
        assert [p.name for p in written] == ["demo_net.json"]
        assert json.loads((tmp_path / "demo_net.json").read_text(encoding="utf-8")) == {"a": [1, 2]}

    def test_ignored_without_json(self, tmp_path):
        assert write_json_output(tmp_path, "demo", "net", {"a": 1}, {"txt"}) == []
