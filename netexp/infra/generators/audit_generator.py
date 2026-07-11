"""Отчёт по классам сетей — преемник старого netclass_audit.py."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from ...core.context import GenerationContext
from ...core.models import NetClassDef, NetKind
from ._common import write_json_output, write_text_outputs

NAME = "audit"


def _by_class(ctx: GenerationContext) -> dict[str, list[str]]:
    by_class: dict[str, list[str]] = defaultdict(list)
    for n in ctx.doc.nets:
        if n.kind == NetKind.UNCONNECTED:
            continue
        by_class[n.netclass or "Default"].append(n.name)
    return by_class


def _fmt_mm(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "—"


def _rule_str(c: NetClassDef) -> str:
    """Компактная сводка правил трассировки — то, что иначе смотрят в Board
    Setup > Net Classes глазами. track/clearance запрошены явно; via и
    diff-pair добавлены заодно, раз источник тот же самый."""
    parts = [f"track={_fmt_mm(c.track_width)}", f"clr={_fmt_mm(c.clearance)}"]
    if c.via_diameter is not None or c.via_drill is not None:
        parts.append(f"via={_fmt_mm(c.via_diameter)}/{_fmt_mm(c.via_drill)}")
    if c.diff_pair_width is not None or c.diff_pair_gap is not None:
        parts.append(f"diffpair={_fmt_mm(c.diff_pair_width)}/{_fmt_mm(c.diff_pair_gap)}")
    return " ".join(parts) + "mm"


def _render_text(ctx: GenerationContext) -> str:
    by_class = _by_class(ctx)
    considered = sum(len(v) for v in by_class.values())

    lines = [f"Цепей (без unconnected): {considered}", ""]
    width = max((len(c.name) for c in ctx.classes), default=7) + 1
    rule_width = max((len(_rule_str(c)) for c in ctx.classes), default=20) + 1
    for c in sorted(ctx.classes, key=lambda c: c.priority):
        names = sorted(by_class.get(c.name, []))
        head = ", ".join(names) if names else "[пусто]"
        lines.append(
            f"[{c.name:<{width}}] prio={c.priority:<3} {_rule_str(c):<{rule_width}} {len(names):3d}: {head}"
        )

    if ctx.overlaps:
        lines.append("")
        lines.append("!! Цепи, попавшие в несколько классов (победил меньший priority):")
        for name, hits in ctx.overlaps:
            lines.append(f"   {name} -> {hits}")

    fell = sorted(by_class.get("Default", []))
    lines.append("")
    lines.append(f"[Default] {len(fell)} цепей — мимо всех паттернов:")
    for n in fell:
        lines.append(f"    {n}")

    if ctx.suspicious:
        lines.append("")
        lines.append(f"!! Подозрительные в Default ({len(ctx.suspicious)}) — проверь руками:")
        for n in ctx.suspicious:
            lines.append(f"    {n}")

    return "\n".join(lines) + "\n"


def _to_json(ctx: GenerationContext) -> dict:
    by_class = _by_class(ctx)
    return {
        "total_considered": sum(len(v) for v in by_class.values()),
        # Правила трассировки каждого класса (track_width/clearance и т.д.) —
        # тот же .kicad_pro, что и netclass_patterns, просто другие поля.
        # None там, где в конкретной версии/классе поля не было.
        "classes": [asdict(c) for c in sorted(ctx.classes, key=lambda c: c.priority)],
        "by_class": {c.name: sorted(by_class.get(c.name, [])) for c in ctx.classes},
        "overlaps": [{"net": n, "classes": h} for n, h in ctx.overlaps],
        "default_unmatched": sorted(by_class.get("Default", [])),
        "suspicious_default": ctx.suspicious,
    }


def generate(ctx: GenerationContext) -> list[Path]:
    written: list[Path] = []
    written += write_text_outputs(ctx.out_dir, ctx.base_name, "audit", _render_text(ctx), ctx.formats)
    written += write_json_output(ctx.out_dir, ctx.base_name, "audit", _to_json(ctx), ctx.formats)
    return written
