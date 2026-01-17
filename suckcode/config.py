"""suckcode configuration management."""

import os
import tomllib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG_PATHS = [
    Path.home() / ".suckcode.toml",           # Global config
    Path.home() / ".config" / "suckcode.toml", # XDG config
    Path(".suckcode.toml"),                    # Local project config
]

@dataclass
class Config:
    """Suckcode configuration."""
    # API Settings
    api_key: str = "openrouter_api_key"
    api_url: str = "https://openrouter.ai/api/v1/chat/completions"
    model: str = "xiaomi/mimo-v2-flash:free"
    max_tokens: int = 8192
    
    # UI Settings
    theme: str = "monokai"
    show_tool_results: bool = True
    stream: bool = True
    
    # Session Settings
    session_dir: Path = field(default_factory=lambda: Path.home() / ".suckcode" / "sessions")
    auto_save: bool = True
    
    # Tool Settings
    bash_timeout: int = 60
    max_file_size: int = 100000  # bytes
    backup_on_edit: bool = True
    
    # MCP Settings
    mcp_servers: dict = field(default_factory=dict)
    
    # Model Aliases
    aliases: dict = field(default_factory=lambda: {
        "opus-4.5": "anthropic/claude-opus-4.5",
        "codex-5.2": "openai/gpt-5.2-codex",
        "gemini-3-flash": "google/gemini-3-flash-preview",
        "mimo": "xiaomi/mimo-v2-flash:free",
    })

def load_config() -> Config:
    """Load configuration from files and environment variables."""
    config = Config()
    
    # Load from config files (later files override earlier)
    for path in CONFIG_PATHS:
        if path.exists():
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                _apply_config(config, data)
            except Exception as e:
                print(f"Warning: Failed to load config from {path}: {e}")
    
    # Environment variables override file config
    if os.environ.get("OPENROUTER_API_KEY"):
        config.api_key = os.environ["OPENROUTER_API_KEY"]
    if os.environ.get("ANTHROPIC_API_KEY") and not config.api_key:
        config.api_key = os.environ["ANTHROPIC_API_KEY"]
        config.api_url = "https://api.anthropic.com/v1/messages"
    if os.environ.get("SUCKCODE_MODEL"):
        config.model = os.environ["SUCKCODE_MODEL"]
    if os.environ.get("SUCKCODE_MAX_TOKENS"):
        config.max_tokens = int(os.environ["SUCKCODE_MAX_TOKENS"])
    
    return config

def _apply_config(config: Config, data: dict):
    """Apply dictionary data to config object."""
    for key, value in data.items():
        if key == "api":
            if "key" in value:
                config.api_key = value["key"]
            if "url" in value:
                config.api_url = value["url"]
            if "model" in value:
                config.model = value["model"]
            if "max_tokens" in value:
                config.max_tokens = value["max_tokens"]
        elif key == "ui":
            if "theme" in value:
                config.theme = value["theme"]
            if "stream" in value:
                config.stream = value["stream"]
        elif key == "session":
            if "dir" in value:
                config.session_dir = Path(value["dir"])
            if "auto_save" in value:
                config.auto_save = value["auto_save"]
        elif key == "tools":
            if "bash_timeout" in value:
                config.bash_timeout = value["bash_timeout"]
            if "backup_on_edit" in value:
                config.backup_on_edit = value["backup_on_edit"]
        elif key == "mcp":
            config.mcp_servers = value.get("servers", {})
        elif key == "aliases":
            config.aliases.update(value)

def resolve_model(config: Config, model_name: str) -> str:
    """Resolve model alias to full model name."""
    return config.aliases.get(model_name, model_name)

def save_config_template(path: Optional[Path] = None):
    """Save a template configuration file."""
    template = '''# SuckCode Configuration
# Copy this to ~/.suckcode.toml or .suckcode.toml in your project

[api]
# key = "your-openrouter-api-key"  # Or set OPENROUTER_API_KEY env var
model = "xiaomi/mimo-v2-flash:free"
max_tokens = 8192

[ui]
theme = "monokai"
stream = true

[session]
auto_save = true

[tools]
bash_timeout = 60
backup_on_edit = true

[aliases]
opus-4.5 = "anthropic/claude-opus-4.5"
codex-5.2 = "openai/gpt-5.2-codex"
gemini-3-flash = "google/gemini-3-flash-preview"
mimo = "xiaomi/mimo-v2-flash:free"

# MCP Server Configuration (optional)
# [mcp.servers.filesystem]
# command = "npx"
# args = ["-y", "@anthropic/mcp-server-filesystem", "/path/to/dir"]
'''
    target = path or Path(".suckcode.toml")
    target.write_text(template)
    return target

# Global config instance
_config: Optional[Config] = None

def get_config() -> Config:
    """Get or load the global config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config

def reload_config():
    """Reload configuration from files."""
    global _config
    _config = load_config()
