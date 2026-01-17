# SuckCode

**Minimal Claude Code Alternative in Python**

## Features

- 🚀 **OpenRouter** - 100+ AI models (Claude, GPT-4, Gemini, Llama...)
- 🛠️ **16 Tools** - File, search, shell, web, git operations
- 💾 **SQLite Sessions** - Persistent conversation history
- 🎨 **Rich TUI** - Panels, syntax highlighting, diffs
- 📁 **Context** - Reads SUCKCODE.md for project context
- 🔌 **MCP Support** - Model Context Protocol integration

## Quick Start

```bash
pip install rich httpx Pillow
export OPENROUTER_API_KEY="your-key"
python -m suckcode
```

## Usage

```bash
python -m suckcode                    # Interactive mode
python -m suckcode -p "explain code"  # Single prompt
python -m suckcode -m claude          # Use model alias
python -m suckcode -s myproject       # Named session
python -m suckcode --init-config      # Create config file
```

## Commands

| Command | Action |
|---------|--------|
| `/c` | Clear conversation |
| `/s` | List sessions |
| `/m MODEL` | Switch model |
| `/d` | Show git diff |
| `/stats` | Session statistics |
| `/q` | Quit |

## Tools

**File**: `read`, `write`, `edit`, `patch`, `ls`  
**Search**: `glob`, `grep`, `find`  
**Shell**: `bash`  
**Web**: `fetch`  
**Git**: `git_status`, `git_diff`, `git_log`, `git_commit`, `git_add`  
**Reasoning**: `think`

## Configuration

Create `~/.suckcode.toml`:

```toml
[api]
model = "anthropic/claude-opus-4.5"

[aliases]
opus-4.5 = "anthropic/claude-opus-4.5"
codex-5.2 = "openai/gpt-5.2-codex"
gemini-3-flash = "google/gemini-3-flash-preview"
mimo = "xiaomi/mimo-v2-flash:free"

[mcp.servers.filesystem]
command = "npx"
args = ["-y", "@anthropic/mcp-server-filesystem", "."]
```

## License

MIT

