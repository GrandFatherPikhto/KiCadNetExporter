"""Отдельный файл для unconnected/no-connect цепей (раньше просто выкидывались)."""
from __future__ import annotations

from pathlib import Path

from ...core.context import GenerationContext
from ...core.models import NetKind
from ._common import pin_sort_key, write_json_output, write_text_outputs

NAME = "unconnected"


def _nets(ctx: GenerationContext):
    return sorted((n for n in ctx.doc.nets if n.kind == NetKind.UNCONNECTED), key=lambda n: n.name)


def _render_text(ctx: GenerationContext) -> str:
    nets = _nets(ctx)
    lines = [f"=== Unconnected / no-connect цепи ({len(nets)}) ===", ""]
    for n in nets:
        pins = ", ".join(f"{p.component_ref}.{p.pin}" for p in sorted(n.pins, key=lambda p: pin_sort_key(p.pin)))
        lines.append(f"  {n.name} -> {pins}")
    return "\n".join(lines) + "\n"


def _to_json(ctx: GenerationContext) -> list[dict]:
    return [
        {"name": n.name, "pins": [f"{p.component_ref}.{p.pin}" for p in n.pins]}
        for n in _nets(ctx)
    ]


def generate(ctx: GenerationContext) -> list[Path]:
    written: list[Path] = []
    written += write_text_outputs(ctx.out_dir, ctx.base_name, "unconnected", _render_text(ctx), ctx.formats)
    written += write_json_output(ctx.out_dir, ctx.base_name, "unconnected", _to_json(ctx), ctx.formats)
    return written
