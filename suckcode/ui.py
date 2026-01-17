"""suckcode UI components using Rich library."""

import os
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.progress import Progress, SpinnerColumn, TextColumn

# ═══════════════════════════════════════════════════════════════════════════════
# Console Instance
# ═══════════════════════════════════════════════════════════════════════════════

console = Console()

# ═══════════════════════════════════════════════════════════════════════════════
# Color Scheme
# ═══════════════════════════════════════════════════════════════════════════════

class Colors:
    """Color constants for the UI."""
    PRIMARY = "cyan"
    SECONDARY = "blue"
    SUCCESS = "green"
    WARNING = "yellow"
    ERROR = "red"
    MUTED = "dim"
    TOOL = "magenta"

# ═══════════════════════════════════════════════════════════════════════════════
# Header & Footer
# ═══════════════════════════════════════════════════════════════════════════════

def print_header(model: str, cwd: Optional[str] = None):
    """Print the application header."""
    cwd = cwd or os.getcwd()
    console.print(Panel.fit(
        f"[bold cyan]suckcode[/bold cyan] - AI Coding Assistant\n"
        f"[dim]Model: {model} | cwd: {cwd}[/dim]",
        border_style="blue"
    ))
    console.print()

def print_footer():
    """Print the footer with commands."""
    console.print(f"[dim]Commands: /c clear, /s sessions, /m model, /d diff, /q quit[/dim]\n")

def separator():
    """Print a separator line."""
    try:
        width = min(os.get_terminal_size().columns, 80)
    except OSError:
        width = 80
    console.print(f"[dim]{'─' * width}[/dim]")

# ═══════════════════════════════════════════════════════════════════════════════
# Message Display
# ═══════════════════════════════════════════════════════════════════════════════

def print_user_prompt():
    """Print the user input prompt indicator."""
    return "[bold blue]❯[/bold blue] "

def print_assistant_start():
    """Print the start of assistant response."""
    console.print(f"\n[cyan]●[/cyan] ", end="")

def print_streaming_text(text: str):
    """Print streaming text (no newline)."""
    console.print(text, end="", markup=False)

def print_message(role: str, content: str):
    """Print a message with role indicator."""
    if role == "user":
        console.print(f"[blue]❯[/blue] {content}")
    elif role == "assistant":
        console.print(f"[cyan]●[/cyan] ", end="")
        try:
            console.print(Markdown(content))
        except:
            console.print(content)
    elif role == "system":
        console.print(f"[dim]⚙ {content}[/dim]")

# ═══════════════════════════════════════════════════════════════════════════════
# Tool Display
# ═══════════════════════════════════════════════════════════════════════════════

def print_tool_call(name: str, args: dict):
    """Print a tool being called."""
    preview = str(list(args.values())[0] if args else "")[:50]
    console.print(f"\n[green]⚡ {name}[/green]([dim]{preview}[/dim])")

def print_tool_result(result: str, max_lines: int = 5):
    """Print tool result (abbreviated)."""
    lines = result.split("\n")
    preview = lines[0][:60]
    if len(lines) > 1:
        preview += f" [dim](+{len(lines)-1} lines)[/dim]"
    elif len(lines[0]) > 60:
        preview += "..."
    console.print(f"   [dim]↳ {preview}[/dim]")

def print_tool_result_full(result: str, language: Optional[str] = None):
    """Print full tool result with optional syntax highlighting."""
    if language:
        syntax = Syntax(result, language, theme="monokai", line_numbers=True)
        console.print(syntax)
    else:
        console.print(Panel(result, border_style="dim"))

# ═══════════════════════════════════════════════════════════════════════════════
# Code Display
# ═══════════════════════════════════════════════════════════════════════════════

def print_code(code: str, language: str = "python", line_numbers: bool = True):
    """Print code with syntax highlighting."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=line_numbers)
    console.print(syntax)

def print_diff(diff_text: str):
    """Print a diff with syntax highlighting."""
    if diff_text.startswith("error") or diff_text == "no changes" or not diff_text.strip():
        console.print(f"[dim]{diff_text}[/dim]")
        return
    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
    console.print(syntax)

def print_file_content(content: str, path: str):
    """Print file content with appropriate syntax highlighting."""
    # Detect language from extension
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "jsx": "jsx", "tsx": "tsx", "json": "json", "yaml": "yaml",
        "yml": "yaml", "toml": "toml", "md": "markdown", "html": "html",
        "css": "css", "sql": "sql", "sh": "bash", "bash": "bash",
        "rs": "rust", "go": "go", "java": "java", "c": "c", "cpp": "cpp",
        "h": "c", "hpp": "cpp", "rb": "ruby", "php": "php"
    }
    language = lang_map.get(ext, "text")
    print_code(content, language)

# ═══════════════════════════════════════════════════════════════════════════════
# Tables & Lists
# ═══════════════════════════════════════════════════════════════════════════════

def print_sessions_table(sessions: list):
    """Print a table of sessions."""
    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return
    
    table = Table(title="Sessions", border_style="dim")
    table.add_column("ID", style="cyan")
    table.add_column("Updated", style="dim")
    table.add_column("Model", style="magenta")
    
    for s in sessions:
        updated = s.updated_at.strftime("%Y-%m-%d %H:%M") if hasattr(s, 'updated_at') else str(s.get('updated_at', ''))[:16]
        model = s.model if hasattr(s, 'model') else s.get('model', '')
        sid = s.id if hasattr(s, 'id') else s.get('id', '')
        table.add_row(sid, updated, model or "-")
    
    console.print(table)

def print_tools_list(tools: list):
    """Print list of available tools."""
    table = Table(title="Available Tools", border_style="dim")
    table.add_column("Tool", style="green")
    table.add_column("Description", style="dim")
    
    for t in tools:
        name = t.name if hasattr(t, 'name') else t.get('name', '')
        desc = t.description if hasattr(t, 'description') else t.get('description', '')
        table.add_row(name, desc[:50])
    
    console.print(table)

# ═══════════════════════════════════════════════════════════════════════════════
# Help & Info
# ═══════════════════════════════════════════════════════════════════════════════

def print_help(tools_list: str):
    """Print help information."""
    console.print(Panel(
        "[bold cyan]Session Commands:[/bold cyan]\n"
        "  /c          Clear conversation\n"
        "  /s          List sessions\n"
        "  /compact    Summarize long conversations\n"
        "  /stats      Show session stats\n"
        "  /q          Quit\n\n"
        "[bold cyan]Model & Config:[/bold cyan]\n"
        "  /m MODEL    Switch model\n"
        "  /init       Generate SUCKCODE.md (fast)\n"
        "  /init ai    Generate SUCKCODE.md (AI-powered)\n\n"
        "[bold cyan]Git & Files:[/bold cyan]\n"
        "  /d          Show git diff\n"
        "  /watch      Start file watcher\n"
        "  /changes    Show file changes\n\n"
        "[bold cyan]Permissions:[/bold cyan]\n"
        "  /auto       Auto-approve all operations\n"
        "  /ask        Prompt for write operations\n\n"
        "[bold cyan]Background Processes:[/bold cyan]\n"
        "  /ps         List background processes\n"
        "  /stop       Stop all background processes\n"
        "  /stop NAME  Stop specific process\n\n"
        "[bold cyan]Images:[/bold cyan]\n"
        "  Include image path in message (e.g., 'analyze screenshot.png')\n\n"
        f"[bold cyan]Tools ({len(tools_list.split(', '))}):[/bold cyan]\n"
        f"  [dim]{tools_list}[/dim]",
        title="Help",
        border_style="cyan"
    ))

def print_stats(stats: dict):
    """Print session statistics."""
    console.print(Panel(
        f"Messages: {stats.get('message_count', 0)}\n"
        f"Tokens: {stats.get('total_tokens', 0):,}\n"
        f"File changes: {stats.get('file_changes', 0)}",
        title="Session Stats",
        border_style="blue"
    ))

# ═══════════════════════════════════════════════════════════════════════════════
# Status & Progress
# ═══════════════════════════════════════════════════════════════════════════════

def print_success(message: str):
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")

def print_error(message: str):
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")

def print_warning(message: str):
    """Print a warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")

def print_info(message: str):
    """Print an info message."""
    console.print(f"[dim]ℹ {message}[/dim]")

class Spinner:
    """Context manager for showing a spinner."""
    def __init__(self, message: str = "Thinking..."):
        self.message = message
        self.progress = None
    
    def __enter__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[dim]{task.description}[/dim]"),
            console=console,
            transient=True
        )
        self.progress.add_task(self.message)
        self.progress.start()
        return self
    
    def __exit__(self, *args):
        if self.progress:
            self.progress.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Input
# ═══════════════════════════════════════════════════════════════════════════════

def get_input(prompt: str = "") -> str:
    """Get user input with styled prompt."""
    try:
        return console.input(f"[bold blue]❯[/bold blue] ").strip()
    except EOFError:
        return "/q"
