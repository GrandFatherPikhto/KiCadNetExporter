"""
Оркестратор: разобрать -> классифицировать -> прогнать все включённые
генераторы. Один прогон = один проект (одна пара .net + .kicad_pro).
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..core.context import GenerationContext
from ..infra.classify import classify_nets
from ..infra.generators import (
    audit_generator,
    bom_generator,
    diff_generator,
    net_generator,
    patterns_generator,
    power_generator,
    raw_copy_generator,
    unconnected_generator,
)
from ..infra.parsers.net_parser import KiCadNetParser
from ..infra.parsers.pro_parser import KiCadProParser
from .config import AppConfig, ProjectConfig

logger = logging.getLogger(__name__)

_GENERATORS = [
    net_generator,
    bom_generator,
    unconnected_generator,
    power_generator,
    audit_generator,
    patterns_generator,
    diff_generator,
]


def run_project(project: ProjectConfig, config: AppConfig) -> list[Path]:
    logger.info("=== Прогон проекта %s ===", project.name)

    net_parser = KiCadNetParser()
    pro_parser = KiCadProParser()

    doc = net_parser.parse(project.netlist)
    classes = pro_parser.parse_classes(project.kicad_project)
    patterns = pro_parser.parse_patterns(project.kicad_project)

    result = classify_nets(
        doc.nets,
        classes,
        patterns,
        power_patterns=config.classification.power_patterns,
        suspicious_patterns=config.classification.suspicious_patterns,
    )

    out_dir = Path(project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = Path(project.netlist).stem

    ctx = GenerationContext(
        doc=doc,
        classes=classes,
        patterns=patterns,
        overlaps=result.overlaps,
        unmatched=result.unmatched,
        suspicious=result.suspicious,
        out_dir=out_dir,
        base_name=base_name,
        formats=set(config.output.formats),
        diff_enabled=config.output.diff,
        snapshot_path=out_dir / f".snapshot_{base_name}.json",
    )

    written: list[Path] = []
    for gen in _GENERATORS:
        try:
            written.extend(gen.generate(ctx))
        except Exception:
            logger.exception("Генератор %s упал на проекте %s", getattr(gen, "NAME", gen), project.name)

    if config.output.raw_txt_copy:
        try:
            written.append(raw_copy_generator.copy_net_as_txt(Path(project.netlist), out_dir))
        except Exception:
            logger.exception("Не удалось скопировать .net в .txt для %s", project.name)

    logger.info("Проект %s: сгенерировано %d файлов в %s", project.name, len(written), out_dir)
    return written
