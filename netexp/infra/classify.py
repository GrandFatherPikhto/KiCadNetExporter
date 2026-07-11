"""
Классификация цепей: netclass по паттернам из .kicad_pro, детект overlaps,
детект unconnected/power/suspicious по паттернам из конфига (не хардкод).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.models import Net, NetClassDef, NetClassPattern, NetKind

_UNCONNECTED_RE = re.compile(r"^unconnected-", re.IGNORECASE)


@dataclass
class ClassificationResult:
    overlaps: list[tuple[str, list[str]]] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    suspicious: list[str] = field(default_factory=list)


def classify_nets(
    nets: list[Net],
    classes: list[NetClassDef],
    patterns: list[NetClassPattern],
    power_patterns: list[str],
    suspicious_patterns: list[str],
) -> ClassificationResult:
    """Мутирует nets на месте (проставляет .netclass и .kind) и возвращает сводку."""
    priority_by_class = {c.name: c.priority for c in classes}

    compiled_patterns: list[tuple[str, re.Pattern, int]] = []
    for p in patterns:
        if not p.compiled_ok:
            continue
        compiled_patterns.append(
            (p.netclass, re.compile(p.pattern), priority_by_class.get(p.netclass, 2**31 - 1))
        )
    compiled_patterns.sort(key=lambda t: t[2])

    power_re = [re.compile(p, re.IGNORECASE) for p in power_patterns]
    suspicious_re = [re.compile(p, re.IGNORECASE) for p in suspicious_patterns]

    result = ClassificationResult()

    for net in nets:
        if _UNCONNECTED_RE.match(net.name):
            net.kind = NetKind.UNCONNECTED
            continue

        hits = [cls for cls, rx, _ in compiled_patterns if rx.search(net.name)]
        if len(hits) > 1:
            result.overlaps.append((net.name, hits))
        net.netclass = hits[0] if hits else "Default"
        if not hits:
            result.unmatched.append(net.name)

        net.kind = NetKind.POWER if any(rx.search(net.name) for rx in power_re) else NetKind.NORMAL

        if net.netclass == "Default" and any(rx.search(net.name) for rx in suspicious_re):
            result.suspicious.append(net.name)

    return result
