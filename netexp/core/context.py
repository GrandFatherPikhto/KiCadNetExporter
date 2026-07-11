"""Контекст генерации — то, что получает каждый OutputGenerator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import NetClassDef, NetClassPattern, NetlistDocument


@dataclass
class GenerationContext:
    doc: NetlistDocument
    classes: list[NetClassDef]
    patterns: list[NetClassPattern]
    overlaps: list[tuple[str, list[str]]]
    unmatched: list[str]
    suspicious: list[str]
    out_dir: Path
    base_name: str
    formats: set[str]  # подмножество {"txt", "json", "md"}
    diff_enabled: bool = True
    snapshot_path: Optional[Path] = None
