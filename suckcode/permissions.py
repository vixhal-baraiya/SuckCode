"""suckcode permissions - Auto-approve tool operations based on patterns."""

import os
import re
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# Permission Rules
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PermissionRule:
    """A rule for auto-approving or denying operations."""
    tool: str  # Tool name or "*" for all
    pattern: str  # Path pattern (glob) or "*" for all
    action: str  # "allow" or "deny"
    
    def matches(self, tool_name: str, path: Optional[str] = None) -> bool:
        """Check if this rule matches the given tool and path."""
        # Check tool match
        if self.tool != "*" and self.tool != tool_name:
            return False
        
        # Check path match if provided
        if path and self.pattern != "*":
            if not fnmatch.fnmatch(path, self.pattern):
                return False
        
        return True

# Default permission rules - only allow rules, everything else prompts user
DEFAULT_RULES = [
    # Auto-allow read operations (safe)
    PermissionRule("read", "*", "allow"),
    PermissionRule("ls", "*", "allow"),
    PermissionRule("glob", "*", "allow"),
    PermissionRule("grep", "*", "allow"),
    PermissionRule("find", "*", "allow"),
    PermissionRule("git_status", "*", "allow"),
    PermissionRule("git_diff", "*", "allow"),
    PermissionRule("git_log", "*", "allow"),
    PermissionRule("changes", "*", "allow"),
    PermissionRule("watch", "*", "allow"),
    PermissionRule("think", "*", "allow"),
    PermissionRule("fetch", "*", "allow"),
    # All other operations (write, edit, bash, git_commit, etc.) will prompt user
]

# ═══════════════════════════════════════════════════════════════════════════════
# Permission Manager
# ═══════════════════════════════════════════════════════════════════════════════

class PermissionManager:
    """Manages tool execution permissions."""
    
    def __init__(self):
        self.rules: list[PermissionRule] = list(DEFAULT_RULES)
        self.mode: str = "ask"  # "ask", "auto", "strict"
        self.approved_this_session: set[str] = set()
        
    def set_mode(self, mode: str):
        """Set permission mode: ask, auto, or strict."""
        if mode in ("ask", "auto", "strict"):
            self.mode = mode
    
    def add_rule(self, tool: str, pattern: str, action: str):
        """Add a permission rule."""
        self.rules.insert(0, PermissionRule(tool, pattern, action))
    
    def check(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """
        Check if a tool execution is allowed.
        Returns (allowed, reason).
        """
        # Extract path from args if present
        path = args.get("path") or args.get("file") or args.get("save_path")
        command = args.get("command", "")
        
        # Check rules in order
        for rule in self.rules:
            # For bash, check command against pattern
            if tool_name == "bash" and rule.tool == "bash":
                if rule.pattern != "*" and rule.pattern in command:
                    if rule.action == "deny":
                        return False, f"Denied: command matches blocked pattern '{rule.pattern}'"
                    continue
            
            if rule.matches(tool_name, path):
                if rule.action == "deny":
                    return False, f"Denied: matches rule {rule.tool}:{rule.pattern}"
                elif rule.action == "allow":
                    return True, "Auto-approved by rule"
        
        # Mode-based decision
        if self.mode == "auto":
            return True, "Auto mode enabled"
        elif self.mode == "strict":
            return False, "Strict mode - requires explicit approval"
        
        # Ask mode - check if already approved this session
        key = f"{tool_name}:{path or command}"
        if key in self.approved_this_session:
            return True, "Previously approved this session"
        
        return None, "Requires approval"  # None means ask user
    
    def approve(self, tool_name: str, args: dict):
        """Mark a tool call as approved for this session."""
        path = args.get("path") or args.get("file") or args.get("command", "")
        key = f"{tool_name}:{path}"
        self.approved_this_session.add(key)
    
    def approve_all(self, tool_name: str):
        """Auto-approve all calls to a tool for this session."""
        self.add_rule(tool_name, "*", "allow")

# ═══════════════════════════════════════════════════════════════════════════════
# Global Permission Manager
# ═══════════════════════════════════════════════════════════════════════════════

_manager: Optional[PermissionManager] = None

def get_permission_manager() -> PermissionManager:
    """Get or create the global permission manager."""
    global _manager
    if _manager is None:
        _manager = PermissionManager()
    return _manager

def check_permission(tool_name: str, args: dict) -> tuple[bool, str]:
    """Check if a tool call is allowed."""
    return get_permission_manager().check(tool_name, args)

def approve_tool(tool_name: str, args: dict):
    """Approve a tool call."""
    get_permission_manager().approve(tool_name, args)

def set_permission_mode(mode: str):
    """Set the permission mode."""
    get_permission_manager().set_mode(mode)

# ═══════════════════════════════════════════════════════════════════════════════
# User Prompts
# ═══════════════════════════════════════════════════════════════════════════════

def prompt_for_permission(tool_name: str, args: dict) -> bool:
    """Ask user for permission to execute a tool."""
    try:
        from .ui import console, print_warning
    except ImportError:
        from ui import console, print_warning
    
    path = args.get("path") or args.get("file") or args.get("command", "")[:50]
    
    console.print(f"\n[yellow]⚠ Permission required:[/yellow]")
    console.print(f"  Tool: [cyan]{tool_name}[/cyan]")
    if path:
        console.print(f"  Target: [dim]{path}[/dim]")
    
    try:
        response = console.input("[yellow]Allow? (y/n/a=always): [/yellow]").strip().lower()
        
        if response == "y":
            approve_tool(tool_name, args)
            return True
        elif response == "a":
            get_permission_manager().approve_all(tool_name)
            console.print(f"[green]✓ Auto-approving all {tool_name} calls[/green]")
            return True
        else:
            return False
    except (EOFError, KeyboardInterrupt):
        return False
