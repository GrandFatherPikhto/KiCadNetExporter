"""Группировка цепей в дерево по путям листов (для net_generator)."""
from __future__ import annotations

from typing import Any, Iterator

from ..core.models import Net


def build_tree(nets: list[Net]) -> dict[str, Any]:
    """
    Строит дерево вида {"_nets": [...], "<лист>": {"_nets": [...], ...}, ...}
    по net.sheet_path каждой цепи.
    """
    root: dict[str, Any] = {"_nets": []}
    for net in nets:
        node = root
        for segment in net.sheet_path:
            node = node.setdefault(segment, {"_nets": []})
        node["_nets"].append(net)
    return root


def iter_tree(node: dict[str, Any], path: list[str] | None = None) -> Iterator[tuple[list[str], list[Net]]]:
    """Обходит дерево в глубину, корень первым: yields (путь_листа, [Net, ...])."""
    path = path or []
    yield path, node.get("_nets", [])
    for key in sorted(k for k in node if k != "_nets"):
        yield from iter_tree(node[key], path + [key])
