"""
Core data models.

Эти модели намеренно повторяют форму NetlistDocument / Component / Net /
PinConnection из сестринского C#-проекта (NetFileConverter.Core), чтобы
JSON, выгруженный одним инструментом, в принципе мог быть прочитан другим.
Поля, специфичные для netclass-логики KiCad, добавлены поверх и не ломают
эту совместимость — это опциональные надстройки, а не замена базовых полей.

core ничего не знает про YAML, watchdog, трей и т.д. — только данные.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


@dataclass
class PinConnection:
    component_ref: str
    pin: str


@dataclass
class Component:
    ref: str
    value: str = "~"
    footprint: str = "~"
    missing_footprint: bool = False


class NetKind(Enum):
    NORMAL = "normal"
    UNCONNECTED = "unconnected"
    POWER = "power"


@dataclass
class Net:
    name: str  # полное иерархическое имя, как в KiCad, напр. "/Power/SubSheetA/+3V3"
    pins: list[PinConnection] = field(default_factory=list)
    netclass: Optional[str] = None
    kind: NetKind = NetKind.NORMAL

    @property
    def sheet_path(self) -> list[str]:
        """Сегменты пути листа, извлечённые из иерархического имени цепи."""
        parts = self.name.strip("/").split("/")
        return parts[:-1] if len(parts) > 1 else []

    @property
    def leaf(self) -> str:
        return self.name.rsplit("/", 1)[-1]


@dataclass
class NetClassDef:
    name: str
    priority: int


@dataclass
class NetClassPattern:
    netclass: str
    pattern: str  # уже нормализованный (после чистки лишних бэкслешей) regex
    compiled_ok: bool = True
    warning: Optional[str] = None


@dataclass
class NetlistDocument:
    source_file_name: str
    format: str = "KiCad"  # зарезервировано для паритета с NetFileConverter (там ещё Protel2)
    parsed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    components: list[Component] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
