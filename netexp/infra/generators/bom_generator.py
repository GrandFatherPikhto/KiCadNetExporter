"""BOM — то, что теряется при упрощении нетлиста, вынесено в отдельный файл."""
from __future__ import annotations

from pathlib import Path

from ...core.context import GenerationContext
from ._common import ref_sort_key, write_json_output, write_text_outputs

NAME = "bom"


def _render_text(ctx: GenerationContext) -> str:
    components = sorted(ctx.doc.components, key=lambda c: ref_sort_key(c.ref))
    missing = [c for c in components if c.missing_footprint]

    lines = [f"=== BOM (список компонентов) для {ctx.doc.source_file_name} ===", ""]
    if missing:
        lines.append("!!! ВНИМАНИЕ: компоненты без посадочного места (footprint) !!!")
        for c in missing:
            lines.append(f"  - {c.ref} (номинал: {c.value})")
        lines.append("")

    width = max((len(c.ref) for c in components), default=10) + 1
    lines.append(f"{'Компонент':<{width}} | {'Номинал':<25} | {'Footprint':<30}")
    lines.append("-" * (width + 60))
    for c in components:
        lines.append(f"{c.ref:<{width}} | {c.value:<25} | {c.footprint:<30}")

    return "\n".join(lines) + "\n"


def _to_json(ctx: GenerationContext) -> list[dict]:
    return [
        {
            "ref": c.ref,
            "value": c.value,
            "footprint": c.footprint,
            "missing_footprint": c.missing_footprint,
        }
        for c in sorted(ctx.doc.components, key=lambda c: ref_sort_key(c.ref))
    ]


def generate(ctx: GenerationContext) -> list[Path]:
    written: list[Path] = []
    written += write_text_outputs(ctx.out_dir, ctx.base_name, "bom", _render_text(ctx), ctx.formats)
    written += write_json_output(ctx.out_dir, ctx.base_name, "bom", _to_json(ctx), ctx.formats)
    return written
