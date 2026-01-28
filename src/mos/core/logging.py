from pathlib import Path

from loguru import logger

from mos.core.config import get_config


def setup_logging():
    """Setup logging based on config"""
    config = get_config()
    log_config = config.log

    # Remove default handler
    logger.remove()

    # Console logging
    if log_config.console_enabled:
        logger.add(
            sink=lambda msg: print(msg, end=""),
            level=log_config.level,
            format=log_config.console_format,
            colorize=True,
        )

    # File logging
    if log_config.file_enabled:
        log_path = Path(log_config.file_path).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            sink=str(log_path),
            level=log_config.level,
            format=log_config.file_format,
            rotation=log_config.file_rotation,
            retention=log_config.file_retention,
            colorize=False,
            backtrace=True,
            diagnose=True,
        )

    return logger


def get_logger(name: str = None):
    """Get a logger instance, optionally with module name"""
    if name:
        return logger.bind(module=name)
    return logger
