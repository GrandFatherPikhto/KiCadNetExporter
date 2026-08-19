"""Тесты протоколов core/interfaces.py (runtime_checkable Protocol)."""
from __future__ import annotations

from netexp.core.interfaces import NetlistParser, OutputGenerator, ProjectParser
from netexp.infra.generators import (  # noqa: F401  (импорт ради наличия модулей)
    audit_generator,
    bom_generator,
    diff_generator,
    net_generator,
    patterns_generator,
    power_generator,
    unconnected_generator,
)
from netexp.infra.parsers.net_parser import KiCadNetParser
from netexp.infra.parsers.pro_parser import KiCadProParser


def test_net_parser_is_protocol():
    assert isinstance(KiCadNetParser(), NetlistParser)


def test_pro_parser_is_project_protocol():
    p = KiCadProParser()
    assert isinstance(p, ProjectParser)


def test_generators_conform_to_protocol():
    for module in (
        audit_generator,
        bom_generator,
        diff_generator,
        net_generator,
        patterns_generator,
        power_generator,
        unconnected_generator,
    ):
        # Каждый генератор обязан предоставлять NAME и generate(ctx),
        # как того требует протокол OutputGenerator.
        assert isinstance(getattr(module, "NAME", None), str)
        assert callable(getattr(module, "generate", None))
        # Сигнатура generate принимает ровно один позиционный аргумент (ctx).
        sig = __import__("inspect").signature(module.generate)
        positional = [p for p in sig.parameters.values()
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        assert len(positional) == 1


def test_negative_conformance():
    """Объект без generate не должен проходить проверку протокола."""
    assert not isinstance(42, OutputGenerator)

    class NotAGenerator:
        pass

    assert not isinstance(NotAGenerator(), OutputGenerator)
