"""
Протоколы, которые реализует слой infra и использует слой app.

Смысл: если завтра появится (или подправят) IPC API KiCad, или понадобится
парсер для другого формата — меняется только реализация в infra,
остальной код, работающий через эти протоколы, не трогается.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .context import GenerationContext
from .models import NetClassDef, NetClassPattern, NetlistDocument


@runtime_checkable
class NetlistParser(Protocol):
    """Разбирает экспортированный нетлист (.net) в core-модель."""

    def parse(self, path: str) -> NetlistDocument: ...


@runtime_checkable
class ProjectParser(Protocol):
    """Читает netclass-определения и паттерны из файла проекта (.kicad_pro)."""

    def parse_classes(self, path: str) -> list[NetClassDef]: ...

    def parse_patterns(self, path: str) -> list[NetClassPattern]: ...


@runtime_checkable
class OutputGenerator(Protocol):
    """Пишет один отчёт/артефакт по классифицированному NetlistDocument."""

    NAME: str  # короткий id, используется в логах/конфиге

    def generate(self, ctx: GenerationContext) -> list[Optional[str]]: ...
