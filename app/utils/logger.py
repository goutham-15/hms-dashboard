import logging
import sys
from pathlib import Path
from datetime import datetime


LOG_DIR = Path("logs")
LOG_FILE = "app.log"

_initialized = False


def _setup_logging():
    """Setup root logger with single file and console handlers."""
    global _initialized
    
    if _initialized:
        return
    
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file_path = LOG_DIR / LOG_FILE
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    if root_logger.handlers:
        root_logger.handlers.clear()
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    _initialized = True


class Logger:
    """
    A logger wrapper that uses a single shared log file for all loggers.
    """
    
    def __init__(self, name: str = "app"):
        """
        Initialize the Logger.
        
        Args:
            name: Logger name (used to identify the source in logs)
        """
        _setup_logging()
        self.logger = logging.getLogger(name)
    
    def debug(self, message: str, *args, **kwargs):
        """Log debug message."""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log info message."""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log warning message."""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log error message."""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Log critical message."""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """Log exception with traceback."""
        self.logger.exception(message, *args, **kwargs)


def get_logger(name: str = "app") -> Logger:
    """
    Get a logger instance with the specified name.
    All loggers share the same single log file.
    
    Args:
        name: Logger name (used to identify the source in logs)
        
    Returns:
        Logger instance
    """
    return Logger(name=name)


logger = get_logger()
