"""Общие мелочи для генераторов: сортировка ref/pin, запись текст+json."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REF_RE = re.compile(r"([A-Za-z]+)(\d+)?")


def ref_sort_key(ref: str) -> tuple[str, int]:
    m = _REF_RE.match(ref)
    if not m:
        return (ref, 0)
    letters, digits = m.groups()
    return (letters, int(digits) if digits else 0)


def pin_sort_key(pin: str) -> tuple[int, Any]:
    return (0, int(pin)) if pin.isdigit() else (1, pin)


def write_text_outputs(out_dir: Path, base: str, suffix: str, text: str, formats: set[str]) -> list[Path]:
    written = []
    if "txt" in formats:
        out = out_dir / f"{base}_{suffix}.txt"
        out.write_text(text, encoding="utf-8")
        written.append(out)
    if "md" in formats:
        out = out_dir / f"{base}_{suffix}.md"
        out.write_text(text, encoding="utf-8")
        written.append(out)
    return written


def write_json_output(out_dir: Path, base: str, suffix: str, data: Any, formats: set[str]) -> list[Path]:
    if "json" not in formats:
        return []
    out = out_dir / f"{base}_{suffix}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return [out]
