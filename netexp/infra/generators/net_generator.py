"""
Главный отчёт: упрощённый нетлист, сгруппированный деревом по листам
иерархии. Полное имя цепи (с путём) показывается всегда — даже внутри
своей группы, чтобы файл был однозначно читаем без привязки к контексту
(важно и для человека, читающего кусок файла, и для ИИ без полного
контекста). netclass дублируется прямо рядом с именем цепи.
"""
from __future__ import annotations

from pathlib import Path

from ...core.context import GenerationContext
from ...core.models import NetKind
from ..hierarchy import build_tree, iter_tree
from ._common import pin_sort_key, write_json_output, write_text_outputs

NAME = "netlist"


def _sheet_title(path: list[str]) -> str:
    return "/ (корень)" if not path else "/" + "/".join(path)


def _render_text(ctx: GenerationContext) -> str:
    normal_nets = [n for n in ctx.doc.nets if n.kind != NetKind.UNCONNECTED]
    comp_by_ref = {c.ref: c for c in ctx.doc.components}
    tree = build_tree(normal_nets)

    lines = [
        f"# {ctx.base_name} — нетлист (упрощённый)",
        f"Цепей всего: {len(ctx.doc.nets)} (без unconnected: {len(normal_nets)})",
        "",
    ]

    for path, nets in iter_tree(tree):
        if not nets and not path:
            continue
        lines.append(f"## {_sheet_title(path)}")
        for net in sorted(nets, key=lambda n: n.name):
            tag = f"  [{net.netclass}]" if net.netclass else ""
            lines.append(f"  {net.name}{tag}")
            by_ref: dict[str, list[str]] = {}
            for pin in net.pins:
                by_ref.setdefault(pin.component_ref, []).append(pin.pin)
            for ref in sorted(by_ref):
                comp = comp_by_ref.get(ref)
                value = comp.value if comp else "?"
                warn = " [!! НЕТ ФУТПРИНТА !!]" if comp and comp.missing_footprint else ""
                pins_str = ", ".join(sorted(by_ref[ref], key=pin_sort_key))
                lines.append(f"    {ref} ({value}){warn} -> пины: {pins_str}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _to_json(ctx: GenerationContext) -> dict:
    normal_nets = [n for n in ctx.doc.nets if n.kind != NetKind.UNCONNECTED]
    comp_by_ref = {c.ref: c for c in ctx.doc.components}

    nets_json = []
    for net in sorted(normal_nets, key=lambda n: n.name):
        by_ref: dict[str, list[str]] = {}
        for pin in net.pins:
            by_ref.setdefault(pin.component_ref, []).append(pin.pin)
        nodes = [
            {
                "ref": ref,
                "value": comp_by_ref[ref].value if ref in comp_by_ref else "?",
                "missing_footprint": comp_by_ref[ref].missing_footprint if ref in comp_by_ref else False,
                "pins": sorted(pins, key=pin_sort_key),
            }
            for ref, pins in sorted(by_ref.items())
        ]
        nets_json.append(
            {
                "name": net.name,
                "sheet_path": net.sheet_path,
                "netclass": net.netclass,
                "nodes": nodes,
            }
        )

    return {
        "source_file": ctx.doc.source_file_name,
        "total_nets": len(ctx.doc.nets),
        "connected_nets": len(normal_nets),
        "nets": nets_json,
    }


def generate(ctx: GenerationContext) -> list[Path]:
    written: list[Path] = []
    if "txt" in ctx.formats or "md" in ctx.formats:
        written += write_text_outputs(ctx.out_dir, ctx.base_name, "net", _render_text(ctx), ctx.formats)
    written += write_json_output(ctx.out_dir, ctx.base_name, "net", _to_json(ctx), ctx.formats)
    return written
