import logging
import sys
from pathlib import Path
from datetime import datetime

import colorlog


class ProjectLogger:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._setup_logging()
            self._initialized = True

    def _setup_logging(self):
        """Настройка глобального логгера"""
        log_dir = Path(__file__).parents[2] / "logs"
        log_dir.mkdir(exist_ok=True)

        current_date = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"project_{current_date}.log"

        log_level = logging.DEBUG

        file_format = '%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s'
        console_format = '%(log_color)s%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s'

        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        root_logger.handlers.clear()

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(file_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        console_handler = colorlog.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        color_scheme = {
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }

        console_formatter = colorlog.ColoredFormatter(
            console_format,
            log_colors=color_scheme,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        telethon_logger = logging.getLogger('telethon')
        telethon_logger.setLevel(logging.WARNING)

        noisy_modules = ['asyncio', 'httpcore', 'httpx']
        for module in noisy_modules:
            logging.getLogger(module).setLevel(logging.WARNING)

        root_logger.info("=" * 60)
        root_logger.info(f"Логирование инициализировано. Логи записываются в: {log_file}")
        root_logger.info("=" * 60)

    @staticmethod
    def get_logger(name: str = None) -> logging.Logger:
        """
        Получить логгер с указанным именем

        Args:
            name: Имя логгера (обычно __name__ модуля)

        Returns:
            logging.Logger: Настроенный логгер
        """
        if not ProjectLogger._initialized:
            ProjectLogger()

        if name is None:
            name = "root"

        logger = logging.getLogger(name)
        return logger


global_logger = ProjectLogger()


def get_logger(name: str = None) -> logging.Logger:
    """Удобная функция для получения логгера"""
    return ProjectLogger.get_logger(name)
