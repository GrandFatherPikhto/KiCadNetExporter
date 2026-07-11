"""Дамп netclass-паттернов (регекспов/wildcard) из .kicad_pro в отдельный файл."""
from __future__ import annotations

from pathlib import Path

from ...core.context import GenerationContext
from ._common import write_json_output, write_text_outputs

NAME = "patterns"


def _render_text(ctx: GenerationContext) -> str:
    lines = ["=== Netclass-паттерны из .kicad_pro ===", ""]
    for p in ctx.patterns:
        status = "OK" if p.compiled_ok else "ОШИБКА"
        lines.append(f"  [{p.netclass}] {p.pattern!r}  ({status})")
        if p.warning:
            lines.append(f"      !! {p.warning}")
    return "\n".join(lines) + "\n"


def _to_json(ctx: GenerationContext) -> list[dict]:
    return [
        {
            "netclass": p.netclass,
            "pattern": p.pattern,
            "compiled_ok": p.compiled_ok,
            "warning": p.warning,
        }
        for p in ctx.patterns
    ]


def generate(ctx: GenerationContext) -> list[Path]:
    written: list[Path] = []
    written += write_text_outputs(ctx.out_dir, ctx.base_name, "patterns", _render_text(ctx), ctx.formats)
    written += write_json_output(ctx.out_dir, ctx.base_name, "patterns", _to_json(ctx), ctx.formats)
    return written
