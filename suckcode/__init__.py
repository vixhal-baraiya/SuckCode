"""SuckCode - Minimal AI coding assistant. Maximum features, minimum code."""

__version__ = "0.1.0"

from .config import get_config, Config
from .tools import TOOLS, run_tool, get_tools_schema
from .ui import console, print_header, print_help, separator
from .db import get_or_create_session, get_messages, add_message, list_sessions

__all__ = [
    "get_config",
    "Config", 
    "TOOLS",
    "run_tool",
    "get_tools_schema",
    "console",
    "main"
]

def main():
    """Entry point for SuckCode."""
    from .suckcode import main as _main
    _main()
