"""suckcode file watcher - Auto-refresh when files change."""

import os
import time
import threading
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional, Set
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════════
# File Watcher
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FileChange:
    """Represents a file change event."""
    path: str
    event_type: str  # created, modified, deleted
    timestamp: datetime
    
@dataclass  
class WatchedFile:
    """Tracks state of a watched file."""
    path: Path
    mtime: float
    size: int
    hash: Optional[str] = None

class FileWatcher:
    """Watch files for changes and notify callbacks."""
    
    def __init__(self, debounce_seconds: float = 0.5):
        self.watched_paths: Set[Path] = set()
        self.watched_patterns: list[str] = []
        self.file_states: dict[str, WatchedFile] = {}
        self.callbacks: list[Callable[[FileChange], None]] = []
        self.debounce_seconds = debounce_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending_changes: dict[str, FileChange] = {}
        self._last_emit_time: dict[str, float] = {}
    
    def watch(self, path: str | Path):
        """Add a path to watch (file or directory)."""
        path = Path(path).resolve()
        with self._lock:
            self.watched_paths.add(path)
            if path.is_file():
                self._add_file_state(path)
            elif path.is_dir():
                for file in path.rglob("*"):
                    if file.is_file() and not self._should_ignore(file):
                        self._add_file_state(file)
    
    def watch_pattern(self, pattern: str):
        """Add a glob pattern to watch."""
        self.watched_patterns.append(pattern)
    
    def on_change(self, callback: Callable[[FileChange], None]):
        """Register a callback for file changes."""
        self.callbacks.append(callback)
    
    def start(self):
        """Start watching for changes in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop watching for changes."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
    
    def check_once(self) -> list[FileChange]:
        """Check for changes once (synchronous)."""
        changes = []
        
        with self._lock:
            # Check watched paths
            for path in list(self.watched_paths):
                if path.is_dir():
                    changes.extend(self._check_directory(path))
                elif path.is_file():
                    change = self._check_file(path)
                    if change:
                        changes.append(change)
            
            # Check patterns
            for pattern in self.watched_patterns:
                import glob
                for filepath in glob.glob(pattern, recursive=True):
                    path = Path(filepath)
                    if path.is_file() and not self._should_ignore(path):
                        change = self._check_file(path)
                        if change:
                            changes.append(change)
        
        return changes
    
    def get_summary(self) -> str:
        """Get a summary of recent changes."""
        changes = self.check_once()
        if not changes:
            return "No file changes detected."
        
        lines = [f"📁 {len(changes)} file(s) changed:"]
        for c in changes[:10]:
            icon = {"created": "➕", "modified": "✏️", "deleted": "❌"}.get(c.event_type, "•")
            lines.append(f"  {icon} {c.path}")
        if len(changes) > 10:
            lines.append(f"  ... and {len(changes) - 10} more")
        return "\n".join(lines)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Private Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def _watch_loop(self):
        """Main watch loop (runs in background thread)."""
        while self._running:
            try:
                changes = self.check_once()
                for change in changes:
                    self._emit_change(change)
            except Exception as e:
                pass  # Ignore errors in watch loop
            time.sleep(1)  # Check every second
    
    def _emit_change(self, change: FileChange):
        """Emit a change event with debouncing."""
        now = time.time()
        key = change.path
        
        # Debounce
        if key in self._last_emit_time:
            if now - self._last_emit_time[key] < self.debounce_seconds:
                self._pending_changes[key] = change
                return
        
        self._last_emit_time[key] = now
        for callback in self.callbacks:
            try:
                callback(change)
            except Exception:
                pass
    
    def _add_file_state(self, path: Path):
        """Add initial file state."""
        try:
            stat = path.stat()
            self.file_states[str(path)] = WatchedFile(
                path=path,
                mtime=stat.st_mtime,
                size=stat.st_size
            )
        except (OSError, IOError):
            pass
    
    def _check_file(self, path: Path) -> Optional[FileChange]:
        """Check if a single file has changed."""
        key = str(path)
        
        try:
            if not path.exists():
                if key in self.file_states:
                    del self.file_states[key]
                    return FileChange(key, "deleted", datetime.now())
                return None
            
            stat = path.stat()
            
            if key not in self.file_states:
                self._add_file_state(path)
                return FileChange(key, "created", datetime.now())
            
            old_state = self.file_states[key]
            if stat.st_mtime != old_state.mtime or stat.st_size != old_state.size:
                self.file_states[key] = WatchedFile(
                    path=path,
                    mtime=stat.st_mtime,
                    size=stat.st_size
                )
                return FileChange(key, "modified", datetime.now())
            
        except (OSError, IOError):
            pass
        
        return None
    
    def _check_directory(self, dir_path: Path) -> list[FileChange]:
        """Check all files in a directory."""
        changes = []
        
        # Check existing files
        known_files = {s.path for s in self.file_states.values() 
                      if str(s.path).startswith(str(dir_path))}
        
        # Find new and modified files
        try:
            for file in dir_path.rglob("*"):
                if file.is_file() and not self._should_ignore(file):
                    change = self._check_file(file)
                    if change:
                        changes.append(change)
                    known_files.discard(file)
        except (OSError, IOError):
            pass
        
        # Check for deleted files
        for path in known_files:
            if not path.exists():
                key = str(path)
                if key in self.file_states:
                    del self.file_states[key]
                    changes.append(FileChange(key, "deleted", datetime.now()))
        
        return changes
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if a file should be ignored."""
        ignore_patterns = [
            ".git", "__pycache__", ".pyc", ".pyo", 
            "node_modules", ".venv", "venv", ".env",
            ".bak", ".swp", ".tmp", "~"
        ]
        path_str = str(path)
        return any(p in path_str for p in ignore_patterns)

# ═══════════════════════════════════════════════════════════════════════════════
# Global Watcher
# ═══════════════════════════════════════════════════════════════════════════════

_watcher: Optional[FileWatcher] = None

def get_watcher() -> FileWatcher:
    """Get or create the global file watcher."""
    global _watcher
    if _watcher is None:
        _watcher = FileWatcher()
    return _watcher

def start_watching(path: str = "."):
    """Start watching the current directory."""
    watcher = get_watcher()
    watcher.watch(path)
    watcher.start()
    return watcher

def stop_watching():
    """Stop the file watcher."""
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None

def get_file_changes_summary() -> str:
    """Get summary of recent file changes."""
    watcher = get_watcher()
    return watcher.get_summary()
