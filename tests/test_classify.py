"""Тесты классификации цепей: classify_nets."""
from __future__ import annotations

from netexp.core.models import Net, NetClassDef, NetClassPattern, NetKind
from netexp.infra.classify import ClassificationResult, classify_nets

from . import data as T


def _patterns(*pairs) -> list[NetClassPattern]:
    """pairs: (netclass, pattern, compiled_ok?)"""
    out = []
    for item in pairs:
        cls, pat = item[0], item[1]
        ok = item[2] if len(item) > 2 else True
        out.append(NetClassPattern(netclass=cls, pattern=pat, compiled_ok=ok))
    return out


def _classes(priorities: dict[str, int]) -> list[NetClassDef]:
    return [NetClassDef(name=k, priority=v) for k, v in priorities.items()]


def test_unconnected_detected():
    nets = [Net(name="unconnected-(U1-Pad1)")]
    result = classify_nets(nets, [], [], power_patterns=[], suspicious_patterns=[])
    assert nets[0].kind == NetKind.UNCONNECTED
    assert nets[0].netclass is None
    assert result.unmatched == []


def test_no_patterns_default_class():
    nets = [Net(name="GND"), Net(name="SIG")]
    result = classify_nets(nets, _classes({"Default": 1}), [],
                           power_patterns=[], suspicious_patterns=[])
    assert nets[0].netclass == "Default"
    assert nets[1].netclass == "Default"
    assert set(result.unmatched) == {"GND", "SIG"}


def test_pattern_matching_and_priority():
    nets = [Net(name="CLK_100M"), Net(name="DATA")]
    patterns = _patterns(("Clock", "CLK"), ("Data", "DATA"))
    result = classify_nets(
        nets,
        _classes({"Clock": 1, "Data": 2, "Default": 3}),
        patterns,
        power_patterns=[],
        suspicious_patterns=[],
    )
    assert nets[0].netclass == "Clock"
    assert nets[1].netclass == "Data"
    assert result.unmatched == []


def test_lowest_priority_wins_overlap():
    """Если цепь попадает в несколько классов — побеждает меньший priority."""
    nets = [Net(name="PWR_5V")]
    patterns = _patterns(("Broad", "PWR"), ("Specific", "PWR_5V"))
    result = classify_nets(
        nets,
        _classes({"Broad": 10, "Specific": 2, "Default": 999}),
        patterns,
        power_patterns=[],
        suspicious_patterns=[],
    )
    assert nets[0].netclass == "Specific"  # priority 2 < 10
    # в overlaps классы перечислены в порядке приоритета (меньший — первым)
    assert result.overlaps == [("PWR_5V", ["Specific", "Broad"])]


def test_power_kind():
    nets = [Net(name="GND"), Net(name="+5V"), Net(name="SIG")]
    classify_nets(nets, [], [], power_patterns=T.POWER_PATTERNS, suspicious_patterns=[])
    kinds = [n.kind for n in nets]
    assert kinds == [NetKind.POWER, NetKind.POWER, NetKind.NORMAL]


def test_suspicious_only_in_default():
    nets = [Net(name="+3V3"), Net(name="CLK_1"), Net(name="SIG")]
    result = classify_nets(
        nets,
        _classes({"Power": 1, "Default": 2}),
        _patterns(("Power", r"(?i)^\+3V3$")),
        power_patterns=[],
        suspicious_patterns=T.SUSPICIOUS_PATTERNS,
    )
    # +3V3 попал в Power -> не считается подозрительным, хоть паттерн и матчится
    assert nets[0].netclass == "Power"
    assert nets[0].kind == NetKind.NORMAL
    # CLK_1 в Default и ловит подозрительный паттерн clk|clock
    assert nets[1].netclass == "Default"
    # SIG в Default, но ни один подозрительный паттерн не матчится
    assert nets[2].netclass == "Default"
    assert result.suspicious == ["CLK_1"]


def test_classification_result_defaults():
    r = ClassificationResult()
    assert r.overlaps == []
    assert r.unmatched == []
    assert r.suspicious == []


def test_compiled_ok_false_patterns_are_skipped():
    nets = [Net(name="BROKEN_X")]
    patterns = _patterns(("Bad", "BROKEN", False))
    result = classify_nets(
        nets, _classes({"Bad": 1, "Default": 2}), patterns,
        power_patterns=[], suspicious_patterns=[],
    )
    # сломанный паттерн не участвует -> цепь уходит в Default и считается unmatched
    assert nets[0].netclass == "Default"
    assert result.unmatched == ["BROKEN_X"]
