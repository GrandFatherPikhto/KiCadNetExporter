"""Тесты KiCadProParser — разбор .kicad_pro (json) в NetClassDef/NetClassPattern."""
from __future__ import annotations

from netexp.infra.parsers.pro_parser import KiCadProParser

from . import data as T


class TestKiCadProParser:
    def test_parse_classes(self, demo_classes):
        by_name = {c.name: c for c in demo_classes}
        assert set(by_name) == {"Default", "Power", "Clock"}
        assert by_name["Power"].priority == 1
        assert by_name["Clock"].priority == 2
        # правила трассировки
        assert by_name["Power"].track_width == 0.5
        assert by_name["Power"].clearance == 0.2
        assert by_name["Power"].via_diameter == 0.8
        assert by_name["Power"].via_drill == 0.4
        # не указанные поля остаются None
        assert by_name["Clock"].track_width is None
        assert by_name["Default"].track_width is None

    def test_parse_classes_priority_default(self, tmp_path):
        """Класс без поля priority получает максимум (по умолчанию 2**31-1)."""
        pro = tmp_path / "p.kicad_pro"
        pro.write_text('{"net_settings": {"classes": [{"name": "X"}]}}', encoding="utf-8")
        classes = KiCadProParser().parse_classes(str(pro))
        assert classes[0].priority == 2**31 - 1

    def test_parse_classes_missing_section(self, tmp_path):
        pro = tmp_path / "p.kicad_pro"
        pro.write_text('{"foo": 1}', encoding="utf-8")
        assert KiCadProParser().parse_classes(str(pro)) == []

    def test_parse_patterns_cleanup_and_warnings(self, demo_patterns):
        by_cls = {p.netclass: p for p in demo_patterns}
        assert set(by_cls) == {"Power", "Clock", "Ghost", "Broken"}

        # Power: паттерн нормальный, компилируется, без предупреждений
        p_power = by_cls["Power"]
        assert p_power.compiled_ok is True
        assert p_power.warning is None
        assert "\\" not in p_power.pattern or "\\d" in p_power.pattern

        # Clock: лишний бэкслеш перед C вычищен, warning выставлен
        p_clk = by_cls["Clock"]
        assert p_clk.pattern == "CLK.*"
        assert p_clk.compiled_ok is True
        assert p_clk.warning is not None
        assert "бэкслеш" in p_clk.warning

        # Ghost: компилируется, но класс не объявлен в classes -> warning
        p_ghost = by_cls["Ghost"]
        assert p_ghost.pattern == "USB.*"
        assert p_ghost.compiled_ok is True
        assert p_ghost.warning is not None
        assert "не объявлен" in p_ghost.warning

        # Broken: невалидный regex -> compiled_ok=False и warning
        p_broken = by_cls["Broken"]
        assert p_broken.compiled_ok is False
        assert p_broken.warning is not None
        assert "не компилируется" in p_broken.warning

    def test_parse_patterns_empty(self, tmp_path):
        pro = tmp_path / "p.kicad_pro"
        pro.write_text('{"net_settings": {}}', encoding="utf-8")
        assert KiCadProParser().parse_patterns(str(pro)) == []

    def test_parse_invalid_json_raises(self, tmp_path):
        pro = tmp_path / "p.kicad_pro"
        pro.write_text("{not json", encoding="utf-8")
        parser = KiCadProParser()
        try:
            parser.parse_classes(str(pro))
        except Exception as exc:  # JSONDecodeError (после retry)
            assert "Expecting" in str(exc) or "not json" in str(exc)
        else:
            raise AssertionError("ожидалось исключение на битом JSON")
