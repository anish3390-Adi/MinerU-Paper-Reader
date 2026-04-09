import logging
import traceback
from pathlib import Path

from utils.config_manager import config_manager


class ErrorHandler:
    """Centralized logging and error formatting."""

    def __init__(self):
        self.log_level = config_manager.get_env("LOG_LEVEL", "INFO")
        self.logger = self._setup_logger()

    def _setup_logger(self):
        logger = logging.getLogger("PaperReader")
        logger.setLevel(getattr(logging, self.log_level.upper(), logging.INFO))

        if logger.handlers:
            return logger

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        file_handler = logging.FileHandler(Path("paper_reader.log"), encoding="utf-8")
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        logger.propagate = False
        return logger

    def handle_error(self, error, context=None):
        message = str(error)
        formatted = f"{context}: {message}" if context else message
        self.logger.error(formatted)
        self.logger.debug(traceback.format_exc())
        return formatted

    def log_info(self, message):
        self.logger.info(message)


error_handler = ErrorHandler()
