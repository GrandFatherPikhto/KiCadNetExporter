"""Тесты GenerationContext — контейнер, который получают генераторы."""
from __future__ import annotations

from pathlib import Path

from netexp.core.context import GenerationContext


def test_context_fields(classified_doc, demo_classes, demo_patterns):
    ctx = GenerationContext(
        doc=classified_doc,
        classes=demo_classes,
        patterns=demo_patterns,
        overlaps=[("A", ["Power", "Clock"])],
        unmatched=["B"],
        suspicious=["C"],
        out_dir=Path("/tmp/out"),
        base_name="demo",
        formats={"txt", "json"},
        diff_enabled=True,
        snapshot_path=Path("/tmp/out/.snapshot.json"),
    )
    assert ctx.doc is classified_doc
    assert ctx.classes == demo_classes
    assert ctx.patterns == demo_patterns
    assert ctx.overlaps == [("A", ["Power", "Clock"])]
    assert ctx.unmatched == ["B"]
    assert ctx.suspicious == ["C"]
    assert ctx.out_dir == Path("/tmp/out")
    assert ctx.base_name == "demo"
    assert ctx.formats == {"txt", "json"}
    assert ctx.diff_enabled is True
    assert ctx.snapshot_path == Path("/tmp/out/.snapshot.json")


def test_context_defaults(classified_doc):
    ctx = GenerationContext(
        doc=classified_doc,
        classes=[],
        patterns=[],
        overlaps=[],
        unmatched=[],
        suspicious=[],
        out_dir=Path("."),
        base_name="demo",
        formats=set(),
    )
    # diff_enabled и snapshot_path имеют значения по умолчанию
    assert ctx.diff_enabled is True
    assert ctx.snapshot_path is None
    assert ctx.formats == set()
