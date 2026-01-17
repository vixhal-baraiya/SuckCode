"""suckcode tools - All tool implementations."""

import os
import re
import glob as globlib
import subprocess
import shutil
import signal
import atexit
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional
import httpx

# Track running processes for cleanup
_running_processes: list[subprocess.Popen] = []
_background_processes: dict[str, subprocess.Popen] = {}  # Named background processes
_bg_counter = 0

def cleanup_processes():
    """Kill all running child processes."""
    import sys
    # Kill foreground processes
    for proc in _running_processes:
        try:
            if sys.platform == "win32":
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                proc.kill()
        except:
            pass
    _running_processes.clear()
    
    # Kill background processes
    for name, proc in list(_background_processes.items()):
        try:
            if sys.platform == "win32":
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                proc.kill()
        except:
            pass
    _background_processes.clear()

def stop_background(name: str = None) -> str:
    """Stop a background process by name, or all if no name given."""
    import sys
    if name and name in _background_processes:
        proc = _background_processes.pop(name)
        try:
            if sys.platform == "win32":
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                proc.kill()
            return f"Stopped: {name}"
        except:
            return f"Failed to stop: {name}"
    elif name:
        return f"No process named: {name}"
    else:
        # Stop all
        stopped = list(_background_processes.keys())
        cleanup_processes()
        return f"Stopped all: {', '.join(stopped)}" if stopped else "No background processes"

def list_background() -> str:
    """List running background processes."""
    if not _background_processes:
        return "No background processes running"
    lines = ["Background processes:"]
    for name, proc in _background_processes.items():
        status = "running" if proc.poll() is None else "stopped"
        lines.append(f"  • {name} (PID {proc.pid}) - {status}")
    return "\n".join(lines)

# Register cleanup on exit
atexit.register(cleanup_processes)

# ═══════════════════════════════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Tool:
    """Represents a tool that the AI can use."""
    name: str
    description: str
    parameters: dict
    function: Callable
    category: str = "general"

TOOLS: dict[str, Tool] = {}

def tool(name: str, description: str, parameters: dict, category: str = "general"):
    """Decorator to register a tool."""
    def decorator(func: Callable):
        TOOLS[name] = Tool(name, description, parameters, func, category)
        return func
    return decorator

def get_tools_schema() -> list[dict]:
    """Generate OpenAI-compatible function schema for all tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string" if v == "string" else "integer" if v == "number" else v.rstrip("?")}
                        for k, v in t.parameters.items()
                    },
                    "required": [k for k, v in t.parameters.items() if not v.endswith("?")]
                }
            }
        }
        for t in TOOLS.values()
    ]

def run_tool(name: str, args: dict, session_id: Optional[str] = None) -> str:
    """Execute a tool and return the result."""
    try:
        if name not in TOOLS:
            return f"error: unknown tool '{name}'"
        result = str(TOOLS[name].function(args))
        
        # Track file changes if session_id provided
        if session_id and name in ("write", "edit"):
            try:
                from . import db
                path = args.get("path", "")
                db.track_file_change(session_id, path, name)
            except:
                pass
        
        return result
    except Exception as e:
        return f"error: {e}"

def list_tools() -> list[Tool]:
    """List all registered tools."""
    return list(TOOLS.values())

def get_tools_by_category() -> dict[str, list[Tool]]:
    """Get tools grouped by category."""
    categories = {}
    for tool in TOOLS.values():
        if tool.category not in categories:
            categories[tool.category] = []
        categories[tool.category].append(tool)
    return categories

# ═══════════════════════════════════════════════════════════════════════════════
# File Tools
# ═══════════════════════════════════════════════════════════════════════════════

@tool("read", "Read file contents with line numbers", 
      {"path": "string", "offset": "number?", "limit": "number?"}, "file")
def tool_read(args: dict) -> str:
    path = Path(args["path"])
    if not path.exists():
        return f"error: file not found: {path}"
    if path.is_dir():
        return f"error: path is a directory: {path}"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except Exception as e:
        return f"error reading file: {e}"
    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", len(lines)))
    selected = lines[offset:offset + limit]
    return "".join(f"{offset + i + 1:4}│ {line}" for i, line in enumerate(selected))

@tool("write", "Write content to a file (creates directories if needed)", 
      {"path": "string", "content": "string"}, "file")
def tool_write(args: dict) -> str:
    path = Path(args["path"]).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args["content"], encoding="utf-8")
    return f"ok: wrote {len(args['content'])} bytes to {path}"

@tool("edit", "Replace text in file (old must be unique unless all=true)", 
      {"path": "string", "old": "string", "new": "string", "all": "string?"}, "file")
def tool_edit(args: dict) -> str:
    path = Path(args["path"]).resolve()
    if not path.exists():
        return f"error: file not found: {path}"
    text = path.read_text(encoding="utf-8")
    old, new = args["old"], args["new"]
    if old not in text:
        return "error: old string not found in file"
    count = text.count(old)
    replace_all = args.get("all", "").lower() == "true"
    if count > 1 and not replace_all:
        return f"error: old string appears {count} times, must be unique (use all=true)"
    result = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    path.write_text(result, encoding="utf-8")
    return f"ok: replaced {count if replace_all else 1} occurrence(s)"

@tool("patch", "Apply a unified diff patch to a file",
      {"path": "string", "patch": "string"}, "file")
def tool_patch(args: dict) -> str:
    """Apply a unified diff patch to a file."""
    path = Path(args["path"])
    if not path.exists():
        return f"error: file not found: {path}"
    
    # Try using patch command
    try:
        proc = subprocess.run(
            ["patch", str(path)],
            input=args["patch"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if proc.returncode == 0:
            return "ok: patch applied"
        return f"error: {proc.stderr}"
    except FileNotFoundError:
        return "error: patch command not found, please install patch utility"
    except Exception as e:
        return f"error: {e}"

@tool("ls", "List directory contents", {"path": "string?"}, "file")
def tool_ls(args: dict) -> str:
    path = Path(args.get("path", "."))
    if not path.exists():
        return f"error: path not found: {path}"
    if not path.is_dir():
        return f"error: not a directory: {path}"
    entries = []
    for item in sorted(path.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            entries.append(f"📁 {item.name}/")
        else:
            size = item.stat().st_size
            entries.append(f"📄 {item.name} ({size:,} bytes)")
    return "\n".join(entries) or "(empty directory)"

# ═══════════════════════════════════════════════════════════════════════════════
# Search Tools
# ═══════════════════════════════════════════════════════════════════════════════

@tool("glob", "Find files matching pattern, sorted by modification time", 
      {"pattern": "string", "path": "string?"}, "search")
def tool_glob(args: dict) -> str:
    base = args.get("path", ".")
    pattern = f"{base}/{args['pattern']}".replace("//", "/")
    files = globlib.glob(pattern, recursive=True)
    files = sorted(files, key=lambda f: os.path.getmtime(f) if os.path.isfile(f) else 0, reverse=True)
    return "\n".join(files[:50]) or "no files found"

@tool("grep", "Search files for regex pattern", 
      {"pattern": "string", "path": "string?", "context": "number?"}, "search")
def tool_grep(args: dict) -> str:
    pattern = re.compile(args["pattern"])
    base = args.get("path", ".")
    ctx = int(args.get("context", 0))
    hits = []
    for filepath in globlib.glob(f"{base}/**", recursive=True):
        try:
            if not os.path.isfile(filepath):
                continue
            lines = open(filepath, errors="replace").readlines()
            for i, line in enumerate(lines):
                if pattern.search(line):
                    if ctx > 0:
                        start, end = max(0, i - ctx), min(len(lines), i + ctx + 1)
                        snippet = "".join(f"  {lines[j]}" for j in range(start, end))
                        hits.append(f"{filepath}:{i+1}:\n{snippet}")
                    else:
                        hits.append(f"{filepath}:{i+1}: {line.rstrip()}")
        except Exception:
            pass
    return "\n".join(hits[:50]) or "no matches found"

@tool("find", "Find files by name pattern",
      {"name": "string", "path": "string?", "type": "string?"}, "search")
def tool_find(args: dict) -> str:
    """Find files by name pattern."""
    base = Path(args.get("path", "."))
    name_pattern = args["name"]
    file_type = args.get("type", "all")  # file, dir, all
    
    results = []
    try:
        for item in base.rglob(name_pattern):
            if file_type == "file" and not item.is_file():
                continue
            if file_type == "dir" and not item.is_dir():
                continue
            results.append(str(item))
            if len(results) >= 50:
                break
    except Exception as e:
        return f"error: {e}"
    
    return "\n".join(results) or "no files found"

# ═══════════════════════════════════════════════════════════════════════════════
# Shell Tools
# ═══════════════════════════════════════════════════════════════════════════════

@tool("bash", "Execute shell command", {"command": "string", "cwd": "string?", "timeout": "number?"}, "shell")
def tool_bash(args: dict) -> str:
    """Execute shell command with real-time output streaming."""
    import sys
    cwd = args.get("cwd", os.getcwd())
    timeout = int(args.get("timeout", 60))
    
    def kill_proc(proc):
        """Kill process and all children (Windows compatible)."""
        try:
            if sys.platform == "win32":
                # Use taskkill to kill process tree on Windows
                subprocess.run(
                    f"taskkill /F /T /PID {proc.pid}",
                    shell=True,
                    capture_output=True
                )
            else:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except:
            try:
                proc.kill()
            except:
                pass
    
    try:
        # Create process with new process group on Unix
        kwargs = {
            "shell": True,
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1
        }
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
        
        proc = subprocess.Popen(args["command"], **kwargs)
        
        # Track for cleanup on Ctrl+C
        _running_processes.append(proc)
        
        output_lines = []
        try:
            # Stream output line by line
            for line in proc.stdout:
                print(f"  │ {line}", end="", flush=True)
                output_lines.append(line)
                if len(output_lines) > 500:
                    output_lines = output_lines[-500:]
            
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_proc(proc)
            output_lines.append(f"\n(timed out after {timeout}s)")
        except KeyboardInterrupt:
            print("\n  │ (stopping...)")
            kill_proc(proc)
            output_lines.append("\n(interrupted)")
            raise
        finally:
            if proc in _running_processes:
                _running_processes.remove(proc)
        
        output = "".join(output_lines)
        if proc.returncode and proc.returncode != 0:
            output += f"\n(exit code: {proc.returncode})"
        
        return output.strip() or "(no output)"
    except KeyboardInterrupt:
        raise
    except Exception as e:
        return f"error: {e}"

@tool("bash_bg", "Run command in background (for servers). Use /stop to kill later", 
      {"command": "string", "name": "string?", "cwd": "string?"}, "shell")
def tool_bash_bg(args: dict) -> str:
    """Run a command in background, returns immediately."""
    global _bg_counter
    import sys
    import threading
    
    cwd = args.get("cwd", os.getcwd())
    name = args.get("name") or f"bg_{_bg_counter}"
    _bg_counter += 1
    
    try:
        kwargs = {
            "shell": True,
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1
        }
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
        
        proc = subprocess.Popen(args["command"], **kwargs)
        _background_processes[name] = proc
        
        # Start a thread to print output
        def stream_output():
            try:
                for line in proc.stdout:
                    print(f"  [{name}] {line}", end="", flush=True)
            except:
                pass
        
        thread = threading.Thread(target=stream_output, daemon=True)
        thread.start()
        
        return f"Started background process '{name}' (PID {proc.pid}). Use /stop {name} to kill it."
    except Exception as e:
        return f"error: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# Web Tools
# ═══════════════════════════════════════════════════════════════════════════════

@tool("fetch", "Fetch URL content", {"url": "string"}, "web")
def tool_fetch(args: dict) -> str:
    try:
        resp = httpx.get(args["url"], timeout=30, follow_redirects=True)
        resp.raise_for_status()
        content = resp.text[:10000]
        if len(resp.text) > 10000:
            content += f"\n... (truncated, {len(resp.text)} bytes total)"
        return content
    except Exception as e:
        return f"error: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# Git Tools
# ═══════════════════════════════════════════════════════════════════════════════

@tool("git_status", "Get git repository status", {"path": "string?"}, "git")
def tool_git_status(args: dict) -> str:
    cwd = args.get("path", ".")
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-b"],
            cwd=cwd, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return f"error: {result.stderr}"
        output = result.stdout.strip()
        return output or "clean working tree"
    except Exception as e:
        return f"error: {e}"

@tool("git_diff", "Show git diff for file or all changes", 
      {"file": "string?", "staged": "string?"}, "git")
def tool_git_diff(args: dict) -> str:
    cmd = ["git", "diff"]
    if args.get("staged", "").lower() == "true":
        cmd.append("--staged")
    if args.get("file"):
        cmd.append(args["file"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        return output[:8000] if output else "no changes"
    except Exception as e:
        return f"error: {e}"

@tool("git_log", "Show git commit history", {"count": "number?", "oneline": "string?"}, "git")
def tool_git_log(args: dict) -> str:
    count = int(args.get("count", 10))
    cmd = ["git", "log", f"-{count}"]
    if args.get("oneline", "true").lower() == "true":
        cmd.append("--oneline")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or "no commits"
    except Exception as e:
        return f"error: {e}"

@tool("git_commit", "Create a git commit with message",
      {"message": "string", "all": "string?"}, "git")
def tool_git_commit(args: dict) -> str:
    """Create a git commit."""
    cmd = ["git", "commit", "-m", args["message"]]
    if args.get("all", "").lower() == "true":
        cmd.insert(2, "-a")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return f"error: {result.stderr}"
        return result.stdout.strip() or "committed"
    except Exception as e:
        return f"error: {e}"

@tool("git_add", "Stage files for commit",
      {"files": "string"}, "git")
def tool_git_add(args: dict) -> str:
    """Stage files for commit."""
    files = args["files"].split()
    cmd = ["git", "add"] + files
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return f"error: {result.stderr}"
        return f"staged: {' '.join(files)}"
    except Exception as e:
        return f"error: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# Thinking Tool (for extended reasoning)
# ═══════════════════════════════════════════════════════════════════════════════

@tool("think", "Think through a complex problem step by step",
      {"thought": "string"}, "reasoning")
def tool_think(args: dict) -> str:
    """A tool for the AI to think through complex problems."""
    # This tool doesn't do anything - it's a scratchpad for the AI
    return "ok"

# ═══════════════════════════════════════════════════════════════════════════════
# File Watcher Tools
# ═══════════════════════════════════════════════════════════════════════════════

@tool("watch", "Start watching a directory for file changes",
      {"path": "string?"}, "watcher")
def tool_watch(args: dict) -> str:
    """Start watching a directory for changes."""
    try:
        from .watcher import start_watching, get_watcher
    except ImportError:
        from watcher import start_watching, get_watcher
    
    path = args.get("path", ".")
    watcher = start_watching(path)
    return f"ok: watching {path} for changes"

@tool("changes", "Check for recent file changes",
      {"path": "string?"}, "watcher")
def tool_changes(args: dict) -> str:
    """Check for recent file changes."""
    try:
        from .watcher import get_watcher
    except ImportError:
        from watcher import get_watcher
    
    watcher = get_watcher()
    if args.get("path"):
        watcher.watch(args["path"])
    
    return watcher.get_summary()
