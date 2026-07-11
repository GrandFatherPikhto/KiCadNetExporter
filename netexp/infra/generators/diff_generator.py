"""
Diff-отчёт: что изменилось со времени прошлого прогона. Сами отчёты
(_net, _bom, _audit и т.д.) при каждом срабатывании перезаписываются
целиком текущим состоянием — diff дополняет их, а не заменяет.
Состояние прошлого прогона хранится в тихом снапшоте рядом с выводом
(out_dir/.snapshot_<base_name>.json).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ...core.context import GenerationContext
from ...core.models import NetKind
from ._common import write_json_output, write_text_outputs

NAME = "diff"

logger = logging.getLogger(__name__)


def _snapshot_of(ctx: GenerationContext) -> dict:
    return {
        "nets": {n.name: (n.netclass or "Default") for n in ctx.doc.nets if n.kind != NetKind.UNCONNECTED},
        "components": {c.ref: c.value for c in ctx.doc.components},
    }


def generate(ctx: GenerationContext) -> list[Path]:
    if not ctx.diff_enabled or ctx.snapshot_path is None:
        return []

    current = _snapshot_of(ctx)
    previous: dict = {}
    if ctx.snapshot_path.exists():
        try:
            previous = json.loads(ctx.snapshot_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Не удалось прочитать снапшот %s: %s — считаю, что его не было", ctx.snapshot_path, e)

    prev_nets = previous.get("nets", {})
    prev_comps = previous.get("components", {})

    added_nets = sorted(set(current["nets"]) - set(prev_nets))
    removed_nets = sorted(set(prev_nets) - set(current["nets"]))
    reclassified = sorted(
        name for name in set(current["nets"]) & set(prev_nets)
        if current["nets"][name] != prev_nets[name]
    )
    added_comps = sorted(set(current["components"]) - set(prev_comps))
    removed_comps = sorted(set(prev_comps) - set(current["components"]))
    has_changes = any([added_nets, removed_nets, reclassified, added_comps, removed_comps])

    lines = [f"=== Diff с прошлого прогона: {ctx.base_name} ===", ""]
    if not previous:
        lines.append("(снапшота ещё не было — это первый прогон)")
    elif not has_changes:
        lines.append("Изменений нет.")
    else:
        if added_nets:
            lines.append(f"+ Новые цепи ({len(added_nets)}):")
            lines += [f"    + {n}" for n in added_nets]
        if removed_nets:
            lines.append(f"- Пропавшие цепи ({len(removed_nets)}):")
            lines += [f"    - {n}" for n in removed_nets]
        if reclassified:
            lines.append(f"~ Сменили netclass ({len(reclassified)}):")
            lines += [f"    ~ {n}: {prev_nets[n]} -> {current['nets'][n]}" for n in reclassified]
        if added_comps:
            lines.append(f"+ Новые компоненты ({len(added_comps)}): {', '.join(added_comps)}")
        if removed_comps:
            lines.append(f"- Пропавшие компоненты ({len(removed_comps)}): {', '.join(removed_comps)}")

    written: list[Path] = []
    written += write_text_outputs(ctx.out_dir, ctx.base_name, "diff", "\n".join(lines) + "\n", ctx.formats)
    written += write_json_output(
        ctx.out_dir, ctx.base_name, "diff",
        {
            "added_nets": added_nets,
            "removed_nets": removed_nets,
            "reclassified": [
                {"net": n, "from": prev_nets[n], "to": current["nets"][n]} for n in reclassified
            ],
            "added_components": added_comps,
            "removed_components": removed_comps,
        },
        ctx.formats,
    )

    # снапшот обновляем всегда, вне зависимости от того, какие форматы включены
    ctx.snapshot_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

    return written
