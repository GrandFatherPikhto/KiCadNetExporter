"""
Адаптер: sexpdata (общий S-expression токенайзер) + свой семантический слой
поверх -> core.NetlistDocument.

Раньше тут был kinparse — специализированная pyparsing-грамматика под весь
файл .net целиком. На реальном проекте (KiCad 10.0.4, иерархический,
mishin-coil-gen-v1) она упала: секция (design ...) в KiCad 10 содержит
по (sheet ...) с (title_block ...) на каждый лист иерархии, а грамматика
kinparse 1.2.4 (последний релиз, "Fixed to handle KiCad V9") про них не
знает — и валится с ParseException на первом же непредусмотренном узле.

sexpdata не пытается понимать семантику KiCad вообще — только токенизирует
S-выражение в вложенные списки/Symbol. Дальше сами ищем то, что нужно
(components/nets/comp/net/node...), а всё незнакомое (sheet, title_block,
groups, variants, future-поля) молча пропускаем. Это устойчивее к дрейфу
формата KiCad, чем полная грамматика — не потому что sexpdata активнее
поддерживают, а потому что мы в принципе не завязаны на то, что уже знаем.

Тот же принцип уже используется в сестринском C#-проекте
(NetFileConverter.Infrastructure.SExpressionParser) — свой парсер
S-выражений + своя семантика поверх, без внешней "грамматики нетлиста".
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import sexpdata
from sexpdata import Symbol

from ...core.models import Component, Net, NetlistDocument, PinConnection
from .._retry import retry_on_transient_read

logger = logging.getLogger(__name__)

# U1A, U1B -> U1 (секции многосекционных компонентов схлопываются в одну ссылку)
_SECTION_SUFFIX_RE = re.compile(r"^([A-Za-z]+\d+)[A-Za-z]$")


def _clean_ref(ref: str) -> str:
    m = _SECTION_SUFFIX_RE.match(ref)
    return m.group(1) if m else ref


def _sym_name(node: Any) -> Optional[str]:
    """Имя головного символа списка вида [Symbol('comp'), ...], иначе None."""
    if isinstance(node, list) and node and isinstance(node[0], Symbol):
        return str(node[0])
    return None


def _children(node: list, key: str) -> list:
    """Все прямые дети node с головным символом == key."""
    return [c for c in node if _sym_name(c) == key]


def _child(node: list, key: str) -> Any:
    """Первый прямой ребёнок node с головным символом == key, или None."""
    found = _children(node, key)
    return found[0] if found else None


def _scalar(node: list, key: str) -> str:
    """Значение простого поля вида (key <текст>). Пустая строка, если поля нет."""
    c = _child(node, key)
    if c is None or len(c) < 2:
        return ""
    v = c[1]
    if v is None:
        return ""
    return str(v)


def _top_section(tree: list, name: str) -> list:
    """Дети верхнеуровневой секции (напр. 'components' или 'nets'), [] если её нет."""
    sec = _child(tree, name)
    return sec[1:] if sec else []


def _load_tree(p: Path) -> list:
    """
    Читает и парсит .net с защитой от гонки: watcher/первичный прогон могут
    поймать файл в момент, когда KiCad его ещё дописывает. sexpdata на
    неполном/пустом вводе кидает то AssertionError, то AttributeError —
    непредсказуемо, поэтому ловим широко (Exception), но только вот в этом
    узком месте, а не во всём parse().
    """
    def _attempt() -> list:
        text = p.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            raise ValueError("файл прочитан пустым")
        return sexpdata.loads(text)

    return retry_on_transient_read(_attempt, (Exception,), what=f"чтение {p.name}")


class KiCadNetParser:
    """
    Реализует core.interfaces.NetlistParser для файлов .net (экспорт EESCHEMA),
    на базе общего S-expression парсера sexpdata + собственной семантики.
    """

    def parse(self, path: str) -> NetlistDocument:
        p = Path(path)
        tree = _load_tree(p)

        components: dict[str, Component] = {}
        for comp_node in _top_section(tree, "components"):
            if _sym_name(comp_node) != "comp":
                continue
            ref = _clean_ref(_scalar(comp_node, "ref"))
            if not ref or ref in components:
                continue  # многосекционный компонент — первая секция выигрывает
            value = _scalar(comp_node, "value").strip()
            footprint_raw = _scalar(comp_node, "footprint").strip()
            footprint = footprint_raw.split(":")[-1] if footprint_raw else ""
            missing = footprint in ("", "~")
            components[ref] = Component(
                ref=ref,
                value=value or "~",
                footprint="~" if missing else footprint,
                missing_footprint=missing,
            )

        nets: list[Net] = []
        for net_node in _top_section(tree, "nets"):
            if _sym_name(net_node) != "net":
                continue
            name = _scalar(net_node, "name")
            if not name:
                continue
            seen: set[tuple[str, str]] = set()
            pins: list[PinConnection] = []
            for node_node in _children(net_node, "node"):
                ref = _clean_ref(_scalar(node_node, "ref"))
                num = _scalar(node_node, "pin")
                if not ref or not num:
                    continue
                key = (ref, num)
                if key in seen:
                    continue
                seen.add(key)
                pins.append(PinConnection(component_ref=ref, pin=num))
            nets.append(Net(name=name, pins=pins))

        design = _child(tree, "design")
        metadata = {
            "source_sheet": _scalar(design, "source") if design else "",
            "tool": _scalar(design, "tool") if design else "",
            "date": _scalar(design, "date") if design else "",
        }

        doc = NetlistDocument(
            source_file_name=p.name,
            components=list(components.values()),
            nets=nets,
            metadata=metadata,
        )
        logger.info(
            "Разобран %s: %d компонентов, %d цепей",
            p.name, len(doc.components), len(doc.nets),
        )
        return doc
