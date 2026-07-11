"""
Опциональная копия сырого .net в .txt с сохранением времени изменения —
чтобы можно было закинуть файл в инструменты (напр. DeepSeek), которые не
понимают расширение .net.

Работает напрямую с файлом на диске, а не с разобранной моделью — поэтому
не реализует core.interfaces.OutputGenerator и не принимает GenerationContext.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def copy_net_as_txt(net_path: Path, out_dir: Path) -> Path:
    """
    Копирует net_path -> out_dir/<имя>.txt, сохраняя mtime/atime (shutil.copystat).

    Примечание: на Windows время СОЗДАНИЯ файла (то, что Проводник показывает
    отдельно от "изменён") этим не переносится — copystat/os.utime трогают
    только mtime и atime. Если нужен и birthtime — потребуется pywin32
    (win32file.SetFileTime); пока не подключаем ради одной этой мелочи.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / (net_path.stem + ".txt")
    shutil.copyfile(net_path, dest)
    shutil.copystat(net_path, dest)
    logger.info("Скопирован %s -> %s (с сохранением mtime/atime)", net_path.name, dest.name)
    return dest
