#!/usr/bin/env python3
"""suckcode - Minimal AI coding assistant"""

import json
import os
import sys
import argparse
import httpx

# Handle imports for both package and standalone execution
try:
    from .config import get_config, resolve_model
    from .tools import TOOLS, run_tool, get_tools_schema, stop_background, list_background
    from .ui import (
        console, print_header, print_help, separator, print_tool_call, 
        print_tool_result, print_diff, print_success, print_error, 
        print_sessions_table, print_stats
    )
    from .db import (
        get_or_create_session, get_messages, add_message, clear_messages,
        list_sessions, get_session_stats
    )
    from .mcp import get_mcp_client, init_mcp_from_config, shutdown_mcp
    from .images import process_message_with_images, create_message_with_images, load_image
    from .watcher import start_watching, stop_watching, get_file_changes_summary
    from .permissions import check_permission, approve_tool, prompt_for_permission, set_permission_mode
    from .context import compact_conversation, apply_compact, init_suckcode_file, quick_init
except ImportError:
    # Running as standalone script
    from config import get_config, resolve_model
    from tools import TOOLS, run_tool, get_tools_schema, stop_background, list_background
    from ui import (
        console, print_header, print_help, separator, print_tool_call, 
        print_tool_result, print_diff, print_success, print_error, 
        print_sessions_table, print_stats
    )
    from db import (
        get_or_create_session, get_messages, add_message, clear_messages,
        list_sessions, get_session_stats
    )
    from mcp import get_mcp_client, init_mcp_from_config, shutdown_mcp
    from images import process_message_with_images, create_message_with_images, load_image
    from watcher import start_watching, stop_watching, get_file_changes_summary
    from permissions import check_permission, approve_tool, prompt_for_permission, set_permission_mode
    from context import compact_conversation, apply_compact, init_suckcode_file, quick_init

# ═══════════════════════════════════════════════════════════════════════════════
# ANSI Colors (fallback)
# ═══════════════════════════════════════════════════════════════════════════════

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[38;5;75m"
    CYAN = "\033[38;5;87m"
    GREEN = "\033[38;5;114m"
    RED = "\033[38;5;203m"

# ═══════════════════════════════════════════════════════════════════════════════
# OpenRouter API Client
# ═══════════════════════════════════════════════════════════════════════════════

def call_api(messages: list[dict], config, stream: bool = True):
    """Call OpenRouter API with tool support."""
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/suckcode",
        "X-Title": "suckcode"
    }
    
    # Get tools - include MCP tools if available
    tools_schema = get_tools_schema()
    mcp = get_mcp_client()
    if mcp.all_tools:
        tools_schema.extend(mcp.get_tools_schema())
    
    payload = {
        "model": config.model,
        "messages": messages,
        "tools": tools_schema,
        "max_tokens": config.max_tokens,
        "stream": stream
    }
    
    if stream:
        return _stream_response(config.api_url, headers, payload)
    else:
        resp = httpx.post(config.api_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()

def _stream_response(api_url: str, headers: dict, payload: dict):
    """Stream response from API, yielding content and tool calls."""
    with httpx.stream("POST", api_url, headers=headers, json=payload, timeout=120) as resp:
        resp.raise_for_status()
        content_buffer = ""
        tool_calls = []
        
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                
                # Text content
                if "content" in delta and delta["content"]:
                    content_buffer += delta["content"]
                    yield {"type": "content", "text": delta["content"]}
                
                # Tool calls
                if "tool_calls" in delta:
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx >= len(tool_calls):
                            tool_calls.append({"id": "", "name": "", "arguments": ""})
                        if "id" in tc:
                            tool_calls[idx]["id"] = tc["id"]
                        if "function" in tc:
                            if "name" in tc["function"]:
                                tool_calls[idx]["name"] = tc["function"]["name"]
                            if "arguments" in tc["function"]:
                                tool_calls[idx]["arguments"] += tc["function"]["arguments"]
            except json.JSONDecodeError:
                pass
        
        if tool_calls:
            yield {"type": "tool_calls", "calls": tool_calls}
        yield {"type": "done", "content": content_buffer}

# ═══════════════════════════════════════════════════════════════════════════════
# Context Gathering
# ═══════════════════════════════════════════════════════════════════════════════

def gather_context() -> str:
    """Gather project context from SUCKCODE.md, .suckcode, or CLAUDE.md"""
    from pathlib import Path
    context_files = ["SUCKCODE.md", ".suckcode", "CLAUDE.md", ".claude"]
    for name in context_files:
        path = Path(name)
        if path.exists():
            return f"\n<project_context file=\"{name}\">\n{path.read_text()}\n</project_context>\n"
    return ""

def get_system_prompt() -> str:
    """Generate the system prompt with context."""
    ctx = gather_context()
    tools_list = ", ".join(TOOLS.keys())
    
    # Add MCP tools
    mcp = get_mcp_client()
    if mcp.all_tools:
        mcp_tools = [f"mcp_{t.server_name}_{t.name}" for t in mcp.all_tools.values()]
        tools_list += ", " + ", ".join(mcp_tools)
    
    return f"""You are suckcode, an expert AI coding assistant. You help developers with coding tasks directly in the terminal.

Current working directory: {os.getcwd()}
{ctx}
Guidelines:
- Be concise and direct
- Use tools to explore and modify code
- Show file contents before editing
- Explain your changes briefly
- Use bash for running commands, tests, builds
- Use git tools to check status and view diffs
- Use the think tool for complex reasoning

Available tools: {tools_list}"""

# ═══════════════════════════════════════════════════════════════════════════════
# Agentic Loop
# ═══════════════════════════════════════════════════════════════════════════════

def agentic_loop(messages: list[dict], session_id: str, config) -> list[dict]:
    """Run the agentic loop until no more tool calls."""
    from rich.markdown import Markdown
    mcp = get_mcp_client()
    
    while True:
        # Stream response
        console.print(f"\n[cyan]●[/cyan] ", end="")
        
        full_content = ""
        tool_calls = []
        
        for event in call_api(messages, config):
            if event["type"] == "content":
                # Print raw during streaming for responsiveness
                print(event["text"], end="", flush=True)
                full_content += event["text"]
            elif event["type"] == "tool_calls":
                tool_calls = event["calls"]
        
        print()  # newline after streaming
        
        # Re-render as markdown if there's content and no tool calls
        if full_content and not tool_calls:
            console.print()  # blank line
            console.print(Markdown(full_content))
        
        # Add assistant message to db
        add_message(session_id, "assistant", full_content, tool_calls if tool_calls else None)
        
        # Add to conversation
        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]}
                    }
                    for tc in tool_calls
                ]
            })
        else:
            messages.append({"role": "assistant", "content": full_content})
            break  # No tool calls, we're done
        
        # Execute tools
        tool_results = []
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}
            
            print_tool_call(tc["name"], args)
            
            # Check permission
            allowed, reason = check_permission(tc["name"], args)
            if allowed is None:  # Needs user approval
                if not prompt_for_permission(tc["name"], args):
                    result = "Skipped: user denied permission"
                    print_tool_result(result)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result
                    })
                    continue
            elif allowed is False:
                result = f"Blocked: {reason}"
                print_tool_result(result)
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result
                })
                continue
            
            # Check if MCP tool
            if tc["name"].startswith("mcp_"):
                parts = tc["name"][4:].split("_", 1)
                if len(parts) == 2:
                    server_name, tool_name = parts
                    result = mcp.call_tool(server_name, tool_name, args)
                    result = json.dumps(result) if isinstance(result, dict) else str(result)
                else:
                    result = "error: invalid MCP tool name"
            else:
                result = run_tool(tc["name"], args, session_id)
            
            print_tool_result(result)
            
            # Add to db
            add_message(session_id, "tool", result, tool_call_id=tc["id"])
            
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result
            })
        
        messages.extend(tool_results)
    
    return messages

# ═══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # Parse args first (so --help works without API key)
    parser = argparse.ArgumentParser(description="suckcode - AI coding assistant")
    parser.add_argument("-p", "--prompt", help="Single prompt (non-interactive)")
    parser.add_argument("-s", "--session", default="default", help="Session name")
    parser.add_argument("-m", "--model", help="Model to use (or alias)")
    parser.add_argument("-c", "--clear", action="store_true", help="Clear session")
    parser.add_argument("--init-config", action="store_true", help="Create config template")
    args = parser.parse_args()
    
    # Load configuration
    config = get_config()
    
    # Create config template
    if args.init_config:
        from .config import save_config_template
        path = save_config_template()
        print_success(f"Config template created: {path}")
        return
    
    # Clear session
    if args.clear:
        clear_messages(args.session)
        print_success(f"Session '{args.session}' cleared")
        return
    
    # Check API key
    if not config.api_key:
        print_error("OPENROUTER_API_KEY not set")
        console.print("Set it with: export OPENROUTER_API_KEY='your-key'")
        console.print("Or create a config file: python -m suckcode --init-config")
        sys.exit(1)
    
    # Resolve model alias
    if args.model:
        config.model = resolve_model(config, args.model)
    
    # Initialize MCP servers if configured
    if config.mcp_servers:
        init_mcp_from_config(config.mcp_servers)
    
    # Get or create session
    session = get_or_create_session(args.session, config.model)
    
    # Load messages from session
    messages = get_messages(args.session)
    
    # Non-interactive mode
    if args.prompt:
        add_message(args.session, "system", get_system_prompt())
        add_message(args.session, "user", args.prompt)
        messages.append({"role": "system", "content": get_system_prompt()})
        messages.append({"role": "user", "content": args.prompt})
        agentic_loop(messages, args.session, config)
        shutdown_mcp()
        return
    
    # Interactive mode
    print_header(config.model)
    console.print("[dim]Commands: /c clear, /s sessions, /m model, /compact, /watch, /d diff, /q quit[/dim]\n")
    
    # Track if watcher is running
    watcher_active = False
    
    try:
        while True:
            separator()
            try:
                user_input = console.input("[bold blue]❯[/bold blue] ").strip()
            except EOFError:
                break
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input in ("/q", "exit", "quit"):
                print_success("Goodbye!")
                break
            
            if user_input == "/c":
                clear_messages(args.session)
                messages = []
                print_success("Conversation cleared")
                continue
            
            if user_input == "/s":
                sessions = list_sessions()
                print_sessions_table(sessions)
                continue
            
            if user_input.startswith("/m "):
                model_input = user_input[3:].strip()
                config.model = resolve_model(config, model_input)
                print_success(f"Model: {config.model}")
                continue
            
            if user_input == "/d":
                from .tools import tool_git_diff
                diff = tool_git_diff({})
                print_diff(diff)
                continue
            
            if user_input == "/stats":
                stats = get_session_stats(args.session)
                print_stats(stats)
                continue
            
            if user_input == "/help":
                tools_list = ", ".join(TOOLS.keys())
                print_help(tools_list)
                continue
            
            # Image command
            if user_input.startswith("/img "):
                img_path = user_input[5:].strip()
                img = load_image(img_path)
                if img:
                    print_success(f"Image loaded: {img_path} ({len(img.data)} bytes)")
                    console.print("[dim]Include image path in your next message to send with prompt[/dim]")
                else:
                    print_error(f"Failed to load image: {img_path}")
                continue
            
            # File watcher commands
            if user_input == "/watch":
                if not watcher_active:
                    start_watching(".")
                    watcher_active = True
                    print_success("File watcher started")
                else:
                    print_success("File watcher already running")
                continue
            
            if user_input == "/changes":
                summary = get_file_changes_summary()
                console.print(summary)
                continue
            
            # /compact - Summarize conversation
            if user_input == "/compact":
                console.print("[dim]Compacting conversation...[/dim]")
                summary = compact_conversation(messages, call_api, config)
                messages = apply_compact(messages, summary)
                clear_messages(args.session)
                for msg in messages:
                    add_message(args.session, msg["role"], msg.get("content", ""))
                print_success(f"Compacted to {len(messages)} messages")
                console.print(f"[dim]{summary[:200]}...[/dim]")
                continue
            
            # /init - Generate SUCKCODE.md
            if user_input == "/init":
                console.print("[dim]Generating SUCKCODE.md...[/dim]")
                result = quick_init()  # Fast version without AI
                print_success(result)
                continue
            
            if user_input == "/init ai":
                console.print("[dim]Generating SUCKCODE.md with AI...[/dim]")
                result = init_suckcode_file(call_api, config)
                print_success(result)
                continue
            
            # /auto - Toggle auto-approve mode
            if user_input == "/auto":
                set_permission_mode("auto")
                print_success("Auto-approve mode enabled")
                continue
            
            if user_input == "/ask":
                set_permission_mode("ask")
                print_success("Ask mode enabled (will prompt for write operations)")
                continue
            
            # /stop - Stop background processes
            if user_input == "/stop":
                result = stop_background()
                print_success(result)
                continue
            
            if user_input.startswith("/stop "):
                name = user_input[6:].strip()
                result = stop_background(name)
                print_success(result)
                continue
            
            # /ps - List background processes
            if user_input == "/ps":
                result = list_background()
                console.print(result)
                continue
            
            # Regular message
            separator()
            
            # Add system prompt if first message
            if not messages:
                messages.append({"role": "system", "content": get_system_prompt()})
                add_message(args.session, "system", get_system_prompt())
            
            # Process message - check for images if vision model
            text, images = process_message_with_images(user_input, config.model)
            
            if images:
                user_msg = create_message_with_images(text, images)
                console.print(f"[dim]📷 {len(images)} image(s) attached[/dim]")
            else:
                user_msg = {"role": "user", "content": user_input}
            
            messages.append(user_msg)
            add_message(args.session, "user", user_input)
            
            try:
                messages = agentic_loop(messages, args.session, config)
            except httpx.HTTPStatusError as e:
                print_error(f"API error: {e.response.status_code}")
            except Exception as e:
                print_error(str(e))
                
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
    finally:
        shutdown_mcp()
        stop_watching()

if __name__ == "__main__":
    main()
