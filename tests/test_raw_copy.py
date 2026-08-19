"""Тесты raw_copy_generator.copy_net_as_txt."""
from __future__ import annotations

import os
import time as _time

from netexp.infra.generators.raw_copy_generator import copy_net_as_txt


def test_copies_file_with_mtime(tmp_path):
    src = tmp_path / "demo.net"
    src.write_text("(export)", encoding="utf-8")
    # ставим нестандартное mtime, чтобы проверить сохранение
    past = _time.time() - 5000
    os.utime(src, (past, past))

    dest = copy_net_as_txt(src, tmp_path / "out")

    assert dest.name == "demo.txt"
    assert dest.read_text(encoding="utf-8") == "(export)"
    assert abs(dest.stat().st_mtime - past) < 1.0


def test_creates_out_dir(tmp_path):
    src = tmp_path / "demo.net"
    src.write_text("x", encoding="utf-8")
    out_dir = tmp_path / "deep" / "out"
    dest = copy_net_as_txt(src, out_dir)
    assert out_dir.is_dir()
    assert dest.exists()


def test_same_stem_different_suffix(tmp_path):
    src = tmp_path / "my.board.net"
    src.write_text("y", encoding="utf-8")
    dest = copy_net_as_txt(src, tmp_path)
    assert dest.name == "my.board.txt"
