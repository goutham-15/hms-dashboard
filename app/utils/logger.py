import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class Logger:
    """
    A logger class that logs to both file and console with configurable formatting.
    """
    
    def __init__(
        self,
        name: str = "app",
        log_dir: str | Path = "logs",
        log_file: Optional[str] = None,
        level: int = logging.INFO,
        console_level: Optional[int] = None,
        file_level: Optional[int] = None
    ):
        """
        Initialize the Logger.
        
        Args:
            name: Logger name
            log_dir: Directory to store log files
            log_file: Specific log file name (default: app_YYYYMMDD.log)
            level: Default logging level for both console and file
            console_level: Specific level for console (overrides level)
            file_level: Specific level for file (overrides level)
        """
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d")
            log_file = f"{name}_{timestamp}.log"
        
        self.log_file_path = self.log_dir / log_file
        
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        console_level = console_level if console_level is not None else level
        file_level = file_level if file_level is not None else level
        
        console_handler = self._create_console_handler(console_level)
        file_handler = self._create_file_handler(file_level)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def _create_console_handler(self, level: int) -> logging.StreamHandler:
        """Create and configure console handler with colored output."""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        console_format = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        
        return console_handler
    
    def _create_file_handler(self, level: int) -> logging.FileHandler:
        """Create and configure file handler."""
        file_handler = logging.FileHandler(self.log_file_path, mode='a', encoding='utf-8')
        file_handler.setLevel(level)
        
        file_format = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        
        return file_handler
    
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
    
    @classmethod
    def get_logger(
        cls,
        name: str = "app",
        log_dir: str | Path = "logs",
        level: int = logging.INFO
    ) -> "Logger":
        """
        Factory method to get a logger instance.
        
        Args:
            name: Logger name
            log_dir: Directory to store log files
            level: Logging level
            
        Returns:
            Logger instance
        """
        return cls(name=name, log_dir=log_dir, level=level)


def get_logger(
    name: str = "app",
    log_dir: str | Path = "logs",
    level: int = logging.INFO
) -> Logger:
    """
    Convenience function to get a logger instance.
    
    Args:
        name: Logger name
        log_dir: Directory to store log files
        level: Logging level
        
    Returns:
        Logger instance
    """
    return Logger.get_logger(name=name, log_dir=log_dir, level=level)


logger = get_logger()
