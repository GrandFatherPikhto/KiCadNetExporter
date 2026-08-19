"""Тесты группировки цепей в дерево: build_tree / iter_tree."""
from __future__ import annotations

from netexp.core.models import Net
from netexp.infra.hierarchy import build_tree, iter_tree


def _nets(names: list[str]):
    return [Net(name=n) for n in names]


class TestBuildTree:
    def test_flat_nets_at_root(self):
        tree = build_tree(_nets(["GND", "+5V"]))
        assert set(tree) == {"_nets"}
        assert [n.name for n in tree["_nets"]] == ["GND", "+5V"]

    def test_hierarchical_nesting(self):
        tree = build_tree(_nets(["/Power/Filter/+3V3", "/Power/Filter/CLK", "/Power/+5V"]))
        assert "Power" in tree
        assert "Filter" in tree["Power"]
        assert [n.name for n in tree["Power"]["_nets"]] == ["/Power/+5V"]
        assert [n.name for n in tree["Power"]["Filter"]["_nets"]] == [
            "/Power/Filter/+3V3", "/Power/Filter/CLK"]

    def test_empty(self):
        assert build_tree([]) == {"_nets": []}


class TestIterTree:
    def test_depth_first_root_first(self):
        tree = build_tree(_nets(["/A/B/1", "/A/2", "/C/3"]))
        order = [path for path, nets in iter_tree(tree)]
        # корень первым, затем дети по алфавиту, в глубину
        assert order == [[], ["A"], ["A", "B"], ["C"]]

    def test_yields_nets_with_path(self):
        tree = build_tree(_nets(["/A/B/1"]))
        results = list(iter_tree(tree))
        assert results[0] == ([], [])
        assert results[2] == (["A", "B"], [Net(name="/A/B/1")])
