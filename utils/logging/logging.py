import logging
import os
from typing import Optional


class _ContextFilter(logging.Filter):
    def __init__(self, engine_name: str):
        super().__init__()
        self._engine_name = engine_name

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "engine_name"):
            record.engine_name = self._engine_name
        return True


def setup_logging(
        log_file: Optional[str] = None,
        engine_name: str = "main",
        reset_handlers: bool = True,
) -> None:
    # log format
    log_format = (
        '%(asctime)s | %(processName)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d '
        '| [engine=%(engine_name)s] %(message)s'
    )
    date_format = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    # root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if reset_handlers:
        root_logger.handlers.clear()

    # setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(_ContextFilter(engine_name))
    root_logger.addHandler(console_handler)

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_ContextFilter(engine_name))
        root_logger.addHandler(file_handler)

    # disable debug logging for specific libraries to reduce noise
    no_debug_loggers = ['asyncio']
    for lib in no_debug_loggers:
        lib_logger = logging.getLogger(lib)
        lib_logger.setLevel(logging.INFO)
