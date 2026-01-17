"""SuckCode context management - /compact and /init commands."""

import os
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# /compact - Summarize Conversation
# ═══════════════════════════════════════════════════════════════════════════════

COMPACT_PROMPT = """Summarize this conversation into a concise context block. Include:
1. What the user is working on
2. Key decisions made
3. Files modified or created
4. Current state/progress

Format as a brief paragraph (max 200 words) that can replace the full conversation history."""

def compact_conversation(messages: list[dict], call_api_func, config) -> str:
    """Summarize the conversation to save tokens."""
    if len(messages) < 4:
        return "Conversation too short to compact."
    
    # Prepare summary request
    summary_messages = [
        {"role": "system", "content": COMPACT_PROMPT},
        {"role": "user", "content": format_messages_for_summary(messages)}
    ]
    
    # Call API without streaming
    try:
        full_content = ""
        for event in call_api_func(summary_messages, config):
            if event["type"] == "content":
                full_content += event["text"]
        return full_content.strip()
    except Exception as e:
        return f"Error during compact: {e}"

def format_messages_for_summary(messages: list[dict]) -> str:
    """Format messages for summarization."""
    lines = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            lines.append(f"{role}: {content[:500]}")
    return "\n".join(lines[-20:])  # Last 20 messages

def apply_compact(messages: list[dict], summary: str) -> list[dict]:
    """Replace conversation with compacted summary."""
    # Keep system prompt if present
    system_msg = None
    for msg in messages:
        if msg.get("role") == "system":
            system_msg = msg
            break
    
    new_messages = []
    if system_msg:
        new_messages.append(system_msg)
    
    # Add summary as context
    new_messages.append({
        "role": "user",
        "content": f"[Previous conversation summary]\n{summary}\n\n[Continuing from here]"
    })
    new_messages.append({
        "role": "assistant", 
        "content": "I understand the context. I'm ready to continue helping."
    })
    
    return new_messages

# ═══════════════════════════════════════════════════════════════════════════════
# /init - Generate SUCKCODE.md
# ═══════════════════════════════════════════════════════════════════════════════

INIT_PROMPT = """Analyze this project structure and create a SUCKCODE.md file.

Include:
1. Project name and brief description
2. Tech stack detected
3. Key directories and their purpose
4. Common commands (build, test, run)
5. Important files to know about
6. Any coding conventions observed

Keep it concise (under 100 lines). Format as markdown."""

def generate_project_context(cwd: str = ".") -> str:
    """Analyze the project and generate context."""
    cwd = Path(cwd)
    
    lines = ["# Project Structure\n"]
    
    # Get file tree (limited depth)
    lines.append("## Files\n```")
    for item in sorted(cwd.rglob("*")):
        # Skip hidden and common ignore patterns
        rel = item.relative_to(cwd)
        parts = rel.parts
        if any(p.startswith(".") or p in ("node_modules", "__pycache__", "venv", ".git") for p in parts):
            continue
        if len(parts) > 3:  # Limit depth
            continue
        indent = "  " * (len(parts) - 1)
        name = item.name + ("/" if item.is_dir() else "")
        lines.append(f"{indent}{name}")
    lines.append("```\n")
    
    # Detect tech stack
    lines.append("## Detected Files\n")
    detections = {
        "Python": list(cwd.glob("*.py")) + list(cwd.glob("requirements*.txt")) + list(cwd.glob("pyproject.toml")),
        "JavaScript": list(cwd.glob("*.js")) + list(cwd.glob("package.json")),
        "TypeScript": list(cwd.glob("*.ts")) + list(cwd.glob("tsconfig.json")),
        "Rust": list(cwd.glob("Cargo.toml")),
        "Go": list(cwd.glob("go.mod")),
    }
    for lang, files in detections.items():
        if files:
            lines.append(f"- {lang}: {len(files)} files")
    lines.append("")
    
    # Read key config files
    config_files = ["package.json", "pyproject.toml", "Cargo.toml", "go.mod", "README.md"]
    for fname in config_files:
        fpath = cwd / fname
        if fpath.exists():
            try:
                content = fpath.read_text(errors="ignore")[:1000]
                lines.append(f"## {fname}\n```\n{content}\n```\n")
            except:
                pass
    
    return "\n".join(lines)

def init_suckcode_file(call_api_func, config, cwd: str = ".") -> str:
    """Generate and save SUCKCODE.md."""
    # Gather project info
    project_info = generate_project_context(cwd)
    
    # Ask AI to generate the context file
    messages = [
        {"role": "system", "content": INIT_PROMPT},
        {"role": "user", "content": project_info}
    ]
    
    try:
        full_content = ""
        for event in call_api_func(messages, config):
            if event["type"] == "content":
                full_content += event["text"]
        
        # Save to file
        suckcode_path = Path(cwd) / "SUCKCODE.md"
        suckcode_path.write_text(full_content, encoding="utf-8")
        
        return f"Created {suckcode_path}"
    except Exception as e:
        return f"Error: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# Quick project scan (without AI)
# ═══════════════════════════════════════════════════════════════════════════════

def quick_init(cwd: str = ".") -> str:
    """Generate a basic SUCKCODE.md without AI."""
    cwd = Path(cwd)
    
    lines = ["# Project Context\n"]
    
    # Detect project name
    name = cwd.resolve().name
    lines.append(f"Project: **{name}**\n")
    
    # Detect tech stack
    if (cwd / "pyproject.toml").exists() or (cwd / "setup.py").exists():
        lines.append("Stack: Python\n")
    elif (cwd / "package.json").exists():
        lines.append("Stack: Node.js\n")
    elif (cwd / "Cargo.toml").exists():
        lines.append("Stack: Rust\n")
    elif (cwd / "go.mod").exists():
        lines.append("Stack: Go\n")
    
    lines.append("## Guidelines\n")
    lines.append("- Follow existing code style\n")
    lines.append("- Write tests for new features\n")
    lines.append("- Keep commits atomic\n")
    
    lines.append("\n## Commands\n")
    lines.append("```bash\n# Add your common commands here\n```\n")
    
    content = "".join(lines)
    
    suckcode_path = cwd / "SUCKCODE.md"
    suckcode_path.write_text(content, encoding="utf-8")
    
    return f"Created {suckcode_path}"
