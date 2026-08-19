"""
Общие фикстуры для всех тестов проекта.

Всё, что можно построить независимо от диска (модели, классификация),
выносится сюда, чтобы тесты не дублировали настройку данных.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Гарантируем, что корень проекта в sys.path (даже если pytest запущен
# из другого каталога без настроек pythonpath).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from netexp.core.context import GenerationContext  # noqa: E402
from netexp.core.models import (  # noqa: E402
    Component,
    Net,
    NetClassDef,
    NetKind,
    NetlistDocument,
    PinConnection,
)
from netexp.infra.classify import classify_nets  # noqa: E402
from netexp.infra.parsers.net_parser import KiCadNetParser  # noqa: E402
from netexp.infra.parsers.pro_parser import KiCadProParser  # noqa: E402

from . import data as T  # noqa: E402


# ---------------------------------------------------------------------------
# Файлы-образцы во временной директории
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_net_path(tmp_path: Path) -> Path:
    """Путь к файлу с синтетическим .net."""
    p = tmp_path / "demo.net"
    p.write_text(T.SAMPLE_NET, encoding="utf-8")
    return p


@pytest.fixture
def sample_pro_path(tmp_path: Path) -> Path:
    """Путь к файлу с синтетическим .kicad_pro."""
    p = tmp_path / "demo.kicad_pro"
    p.write_text(T.SAMPLE_KICAD_PRO, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Разобранные модели (используют парсеры — это и есть интеграционная проверка)
# ---------------------------------------------------------------------------
@pytest.fixture
def demo_doc(sample_net_path: Path) -> NetlistDocument:
    return KiCadNetParser().parse(str(sample_net_path))


@pytest.fixture
def demo_classes(sample_pro_path: Path) -> list[NetClassDef]:
    return KiCadProParser().parse_classes(str(sample_pro_path))


@pytest.fixture
def demo_patterns(sample_pro_path: Path):
    return KiCadProParser().parse_patterns(str(sample_pro_path))


@pytest.fixture
def classify_result(demo_doc, demo_classes, demo_patterns):
    """Сводка классификации (classify_nets мутирует nets на месте)."""
    return classify_nets(
        demo_doc.nets,
        demo_classes,
        demo_patterns,
        power_patterns=T.POWER_PATTERNS,
        suspicious_patterns=T.SUSPICIOUS_PATTERNS,
    )


@pytest.fixture
def classified_doc(demo_doc, classify_result) -> NetlistDocument:
    """doc с проставленными netclass/kind (мутация в classify_result)."""
    return demo_doc


@pytest.fixture
def ctx(demo_doc, demo_classes, demo_patterns, classify_result, tmp_path: Path) -> GenerationContext:
    """Готовый GenerationContext для генераторов."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    return GenerationContext(
        doc=demo_doc,
        classes=demo_classes,
        patterns=demo_patterns,
        overlaps=classify_result.overlaps,
        unmatched=classify_result.unmatched,
        suspicious=classify_result.suspicious,
        out_dir=out_dir,
        base_name="demo",
        formats={"txt", "json"},
        diff_enabled=True,
        snapshot_path=tmp_path / "out" / ".snapshot_demo.json",
    )


# ---------------------------------------------------------------------------
# Мелкие конструкторы, чтобы не плодить одинаковые списки по тестам
# ---------------------------------------------------------------------------
def make_doc(**overrides) -> NetlistDocument:
    defaults = dict(
        source_file_name="demo.net",
        components=[
            Component(ref="R1", value="10k", footprint="R_0603"),
            Component(ref="U1", value="STM32F103", footprint="LQFP-48"),
            Component(ref="C1", value="100n", footprint="~", missing_footprint=True),
        ],
        nets=[
            Net(name="+5V", pins=[PinConnection("R1", "1")], netclass="Power", kind=NetKind.POWER),
            Net(name="GND", pins=[PinConnection("R1", "2")], netclass="Power", kind=NetKind.POWER),
            Net(name="/PWR/+3V3", pins=[PinConnection("U1", "3")], netclass="Default", kind=NetKind.NORMAL),
            Net(name="unconnected-(U1-Pad4)", pins=[PinConnection("U1", "4")], kind=NetKind.UNCONNECTED),
        ],
    )
    defaults.update(overrides)
    return NetlistDocument(**defaults)


def make_classes() -> list[NetClassDef]:
    return [
        NetClassDef(name="Default", priority=2**31 - 1),
        NetClassDef(name="Power", priority=1, track_width=0.5, clearance=0.2),
        NetClassDef(name="Clock", priority=2),
    ]


def make_context(doc: NetlistDocument | None = None, out_dir=None, **overrides) -> GenerationContext:
    doc = doc or make_doc()
    return GenerationContext(
        doc=doc,
        classes=make_classes(),
        patterns=[],
        overlaps=[],
        unmatched=[],
        suspicious=[],
        out_dir=out_dir or Path("."),
        base_name="demo",
        formats={"txt", "json"},
        diff_enabled=True,
        snapshot_path=None,
        **overrides,
    )
