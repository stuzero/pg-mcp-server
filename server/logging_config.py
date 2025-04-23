# server/logging_config.py
import logging
import sys
import os
import re
from datetime import datetime
import logging.handlers

from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme
from rich.highlighter import RegexHighlighter
from rich.style import Style

# Custom highlighter for important patterns
class MCPHighlighter(RegexHighlighter):
    """Highlights important patterns in log messages."""
    
    # Define regex patterns and their styles
    highlights = [
        # Session IDs - bright magenta
        r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
        # HTTP Status codes - green for success
        r'(200 OK|201 Created|204 No Content)',
        # Key phrases - bright blue
        r'(Created new session|Starting SSE|Yielding read and write streams|Sent endpoint event)',
    ]

    base_style = Style()
    session_id_style = Style(color="bright_magenta")
    http_ok_style = Style(color="bright_green")
    key_phrase_style = Style(color="bright_blue")
    
    def highlight(self, text):
        """Apply highlighting to text."""
        text = super().highlight(text)
        
        # Apply custom highlighting for each pattern
        text = re.sub(
            r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
            lambda m: f"[bright_magenta]{m.group(1)}[/bright_magenta]",
            text
        )
        
        text = re.sub(
            r'(200 OK|201 Created|204 No Content)',
            lambda m: f"[bright_green]{m.group(1)}[/bright_green]",
            text
        )
        
        text = re.sub(
            r'(Created new session|Starting SSE|Yielding read and write streams|Sent endpoint event)',
            lambda m: f"[bright_blue]{m.group(1)}[/bright_blue]",
            text
        )
        
        return text

# Create a custom theme for Rich
custom_theme = Theme({
    "info": "green",
    "warning": "yellow",
    "error": "bold red",
    "debug": "cyan",
    "server.sse": "bright_blue",
    "lowlevel.server": "bright_cyan",
    "resources": "bright_green",
    "tools": "bright_magenta",
    "asyncio": "bright_yellow",
})

def get_component_style(name):
    """Get the style for a component based on its name."""
    if "server.sse" in name:
        return "bright_blue"
    elif "lowlevel.server" in name:
        return "bright_cyan"
    elif "resources" in name:
        return "bright_green"
    elif "tools" in name:
        return "bright_magenta"
    elif "asyncio" in name:
        return "bright_yellow"
    else:
        return "bright_black"

class MCPLogFormatter(logging.Formatter):
    """Formatter for non-Rich log handlers that maintains consistent format."""
    
    def format(self, record):
        # Extract component info from the original record
        name_parts = record.name.split('.')
        
        # Determine component
        if len(name_parts) > 1:
            component = record.name
        else:
            component = record.name
            
        # Add component to record
        record.component = f"[{component}]"
        
        # Get source file reference
        source_info = ""
        if hasattr(record, 'pathname') and record.pathname:
            source_file = os.path.basename(record.pathname)
            source_info = f"({source_file}:{record.lineno})"
        record.source_info = source_info
        
        # Format using the base formatter
        return super().format(record)

def configure_logging(level="INFO", log_file=None):
    """
    Configure logging with Rich formatting for the terminal
    and regular formatting for log files.
    
    Args:
        level: The log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to a log file
    """
    # Get log level from environment if available
    env_level = os.environ.get("LOG_LEVEL", level)
    numeric_level = getattr(logging, env_level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to prevent duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create Rich console with custom highlighting
    console = Console(theme=custom_theme, highlighter=MCPHighlighter())
    
    # Rich handler for console output
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=True,  # We'll show the path in our format
        enable_link_path=True,
        markup=True,
        omit_repeated_times=False,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        log_time_format="%Y-%m-%d %H:%M:%S.%f"
    )
    
    # Set the format for Rich handler (minimal since Rich adds its own formatting)
    rich_format = "%(message)s"
    rich_handler.setFormatter(logging.Formatter(rich_format))
    rich_handler.setLevel(numeric_level)
    root_logger.addHandler(rich_handler)
    
    # Add file handler if log file is specified
    if log_file:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Define format for file logs (no color codes)
        file_format = "%(asctime)s | %(levelname)s %(component)s | %(message)s %(source_info)s"
        
        # Create and add rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(MCPLogFormatter(file_format))
        file_handler.setLevel(numeric_level)
        root_logger.addHandler(file_handler)
    
    # Create a logger for the pg-mcp application
    app_logger = logging.getLogger("pg-mcp")
    app_logger.setLevel(numeric_level)
    
    # Log startup message
    app_logger.info(f"Logging configured with level {env_level}")
    
    return root_logger

def get_logger(name):
    """
    Get a logger with the given name, preserving the original naming scheme.
    
    Args:
        name: Logger name
        
    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)

def configure_uvicorn_logging(log_level="info"):
    """
    Configure Uvicorn's logging to match our style.
    
    Args:
        log_level: Log level for Uvicorn
        
    Returns:
        Dictionary with Uvicorn log config
    """
    # Map our log level format to Uvicorn's
    level = log_level.upper()
    if level == "DEBUG":
        log_level = "debug"
    elif level == "INFO":
        log_level = "info"
    elif level == "WARNING":
        log_level = "warning"
    elif level == "ERROR":
        log_level = "error"
    elif level == "CRITICAL":
        log_level = "critical"
    
    # Use default Uvicorn logging config to avoid conflicts
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "log_level": log_level,
    }