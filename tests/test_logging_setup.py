"""Тесты setup_logging — настройка корневого логгера из конфига."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from netexp.app.config import LoggingConfig
from netexp.app.logging_setup import setup_logging


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    saved = list(root.handlers)
    saved_level = root.level
    yield root
    root.handlers[:] = saved
    root.setLevel(saved_level)


def test_returns_absolute_log_path(tmp_path, clean_root_logger):
    cfg = LoggingConfig(level="INFO", file="logs/app.log", console=False)
    result = setup_logging(cfg, base_dir=tmp_path)
    assert result is not None
    assert result.is_absolute()
    assert result == tmp_path / "logs" / "app.log"
    assert result.parent.is_dir()

    # реальная запись в лог попадает в файл
    logging.getLogger("test_logging").info("hello from test")
    assert "hello from test" in result.read_text(encoding="utf-8")


def test_absolute_path_kept_as_is(tmp_path, clean_root_logger):
    target = tmp_path / "custom.log"
    cfg = LoggingConfig(file=str(target), console=False)
    result = setup_logging(cfg, base_dir=tmp_path)
    assert result == target


def test_no_file_returns_none(tmp_path, clean_root_logger):
    cfg = LoggingConfig(file="", console=False)
    assert setup_logging(cfg, base_dir=tmp_path) is None


def test_root_gets_configured_handler(tmp_path, clean_root_logger):
    cfg = LoggingConfig(file="app.log", console=False)
    setup_logging(cfg, base_dir=tmp_path)
    assert any(isinstance(h, logging.handlers.RotatingFileHandler)
               for h in logging.getLogger().handlers)
