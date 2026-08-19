"""Тесты core-моделей: Component, Net, NetClassDef, NetlistDocument, NetKind."""
from __future__ import annotations

from netexp.core.models import (
    Component,
    Net,
    NetClassDef,
    NetKind,
    NetlistDocument,
    PinConnection,
)


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------
class TestComponent:
    def test_defaults(self):
        c = Component(ref="R1")
        assert c.value == "~"
        assert c.footprint == "~"
        assert c.missing_footprint is False

    def test_explicit_fields(self):
        c = Component(ref="R1", value="10k", footprint="R_0603")
        assert c.ref == "R1"
        assert c.value == "10k"
        assert c.footprint == "R_0603"

    def test_missing_footprint_flag(self):
        c = Component(ref="C1", footprint="~", missing_footprint=True)
        assert c.missing_footprint is True


# ---------------------------------------------------------------------------
# Net
# ---------------------------------------------------------------------------
class TestNet:
    def test_sheet_path_hierarchical(self):
        n = Net(name="/Power/SubSheetA/+3V3")
        assert n.sheet_path == ["Power", "SubSheetA"]

    def test_sheet_path_flat(self):
        n = Net(name="GND")
        assert n.sheet_path == []

    def test_sheet_path_deep_no_leading_slash(self):
        n = Net(name="Power/+3V3")
        assert n.sheet_path == ["Power"]

    def test_leaf(self):
        assert Net(name="/Power/SubSheetA/+3V3").leaf == "+3V3"

    def test_leaf_flat(self):
        assert Net(name="GND").leaf == "GND"

    def test_pins_default_empty(self):
        assert Net(name="X").pins == []

    def test_default_netclass_and_kind(self):
        n = Net(name="X")
        assert n.netclass is None
        assert n.kind == NetKind.NORMAL


# ---------------------------------------------------------------------------
# NetClassDef
# ---------------------------------------------------------------------------
class TestNetClassDef:
    def test_defaults_are_none(self):
        c = NetClassDef(name="Default", priority=1)
        assert c.track_width is None
        assert c.clearance is None
        assert c.via_diameter is None
        assert c.diff_pair_gap is None

    def test_rules(self):
        c = NetClassDef(name="Power", priority=1, track_width=0.5, clearance=0.2)
        assert c.track_width == 0.5
        assert c.clearance == 0.2


# ---------------------------------------------------------------------------
# NetKind
# ---------------------------------------------------------------------------
class TestNetKind:
    def test_values(self):
        assert NetKind.NORMAL.value == "normal"
        assert NetKind.UNCONNECTED.value == "unconnected"
        assert NetKind.POWER.value == "power"


# ---------------------------------------------------------------------------
# NetlistDocument
# ---------------------------------------------------------------------------
class TestNetlistDocument:
    def test_defaults(self):
        doc = NetlistDocument(source_file_name="x.net")
        assert doc.format == "KiCad"
        assert doc.components == []
        assert doc.nets == []
        assert doc.metadata == {}
        assert doc.parsed_at is not None

    def test_holds_data(self):
        doc = NetlistDocument(
            source_file_name="x.net",
            components=[Component(ref="R1")],
            nets=[Net(name="GND")],
            metadata={"tool": "Eeschema"},
        )
        assert len(doc.components) == 1
        assert len(doc.nets) == 1
        assert doc.metadata["tool"] == "Eeschema"

    def test_pin_connection_fields(self):
        pc = PinConnection(component_ref="U1", pin="12")
        assert pc.component_ref == "U1"
        assert pc.pin == "12"
