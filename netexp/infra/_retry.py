"""
Защита от гонки "файл ещё не дописан".

Фоновый вотчер (и первичный прогон при старте) может поймать .net/.kicad_pro
в момент, когда KiCad (или синхронизация OneDrive/облака) ещё не закончил
запись — файл на диске уже существует, но временно пуст или обрезан.
Поймано на реальном проекте: json.load падал с "Expecting value: line 1
column 1 (char 0)" на файле, который через долю секунды прекрасно парсился.

Не полагаемся на "подождать и понадеяться" один раз — просто повторяем
чтение+разбор при ошибках, с небольшой паузой, и сдаёмся только после
нескольких попыток (тогда это уже не гонка, а реально пустой/битый файл).
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_RETRIES = 5
DEFAULT_DELAY_SEC = 0.2


def retry_on_transient_read(
    attempt_fn: Callable[[], T],
    exceptions: tuple[type[BaseException], ...],
    what: str,
    retries: int = DEFAULT_RETRIES,
    delay_sec: float = DEFAULT_DELAY_SEC,
) -> T:
    """
    Вызывает attempt_fn(). Если она падает с одним из exceptions — короткая
    пауза и повтор. После исчерпания попыток пробрасывает последнюю ошибку
    как есть (без подмены), чтобы traceback остался честным и понятным.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            return attempt_fn()
        except exceptions as e:
            last_exc = e
            if attempt < retries:
                logger.warning(
                    "%s: попытка %d/%d не удалась (%s: %s) — похоже, файл ещё "
                    "дописывается, жду %.1fс и пробую снова",
                    what, attempt, retries, type(e).__name__, e, delay_sec,
                )
                time.sleep(delay_sec)
            else:
                logger.error(
                    "%s: не удалось прочитать после %d попыток — файл, похоже, "
                    "реально пуст/повреждён, а не просто дописывается",
                    what, retries,
                )
    assert last_exc is not None
    raise last_exc
