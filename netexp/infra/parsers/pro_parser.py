"""
Парсер .kicad_pro. Формат — обычный JSON, отдельная библиотека не нужна:
стандартный json уже и есть "свой парсер под свой формат", в отличие от
S-выражений .net.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ...core.models import NetClassDef, NetClassPattern

logger = logging.getLogger(__name__)

# KiCad иногда пишет паттерны с лишним бэкслешем перед заглавными буквами
# (напр. "\CLK.*") — для re это не нужно, но сам KiCad это проглатывает.
_BAD_ESCAPE_RE = re.compile(r"\\([CLIMRXYZ])")


class KiCadProParser:
    """Реализует core.interfaces.ProjectParser для файлов .kicad_pro."""

    def _load(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def parse_classes(self, path: str) -> list[NetClassDef]:
        pro = self._load(path)
        classes = pro.get("net_settings", {}).get("classes", [])
        return [
            NetClassDef(name=c["name"], priority=c.get("priority", 2**31 - 1))
            for c in classes
        ]

    def parse_patterns(self, path: str) -> list[NetClassPattern]:
        pro = self._load(path)
        ns = pro.get("net_settings", {})
        raw_patterns = ns.get("netclass_patterns", [])
        known_classes = {c["name"] for c in ns.get("classes", [])}

        result: list[NetClassPattern] = []
        for entry in raw_patterns:
            cls, pat = entry["netclass"], entry["pattern"]
            fixed = _BAD_ESCAPE_RE.sub(r"\1", pat)

            warning = None
            if fixed != pat:
                warning = f"лишний бэкслеш в паттерне ({pat!r}) — KiCad проглотит, но лучше почистить руками"

            compiled_ok = True
            try:
                re.compile(fixed)
            except re.error as e:
                compiled_ok = False
                warning = f"паттерн не компилируется: {e}"
                logger.warning("Класс %s: паттерн %r не компилируется: %s", cls, pat, e)

            if cls not in known_classes:
                extra = f"класс {cls!r} не объявлен в classes — в KiCad этот паттерн молча не сработает"
                warning = f"{warning}; {extra}" if warning else extra
                logger.warning("Паттерн ссылается на неизвестный класс %r", cls)

            result.append(
                NetClassPattern(netclass=cls, pattern=fixed, compiled_ok=compiled_ok, warning=warning)
            )
        return result
