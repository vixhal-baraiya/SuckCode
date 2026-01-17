"""SuckCode MCP (Model Context Protocol) client."""

import json
import subprocess
import threading
import queue
from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# MCP Data Types
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MCPTool:
    """Represents a tool provided by an MCP server."""
    name: str
    description: str
    input_schema: dict
    server_name: str

@dataclass
class MCPResource:
    """Represents a resource provided by an MCP server."""
    uri: str
    name: str
    description: str
    mime_type: Optional[str] = None
    server_name: str = ""

@dataclass
class MCPServer:
    """Represents an MCP server connection."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    process: Optional[subprocess.Popen] = None
    tools: list[MCPTool] = field(default_factory=list)
    resources: list[MCPResource] = field(default_factory=list)
    _request_id: int = 0
    _pending: dict = field(default_factory=dict)
    _reader_thread: Optional[threading.Thread] = None
    _response_queue: queue.Queue = field(default_factory=queue.Queue)

# ═══════════════════════════════════════════════════════════════════════════════
# MCP Client
# ═══════════════════════════════════════════════════════════════════════════════

class MCPClient:
    """Client for connecting to MCP servers."""
    
    def __init__(self):
        self.servers: dict[str, MCPServer] = {}
        self.all_tools: dict[str, MCPTool] = {}
        self.all_resources: dict[str, MCPResource] = {}
    
    def add_server(self, name: str, command: str, args: list[str] = None, 
                   env: dict[str, str] = None) -> MCPServer:
        """Add an MCP server configuration."""
        server = MCPServer(
            name=name,
            command=command,
            args=args or [],
            env=env or {}
        )
        self.servers[name] = server
        return server
    
    def connect(self, server_name: str) -> bool:
        """Connect to an MCP server and discover its capabilities."""
        if server_name not in self.servers:
            return False
        
        server = self.servers[server_name]
        
        try:
            # Start the server process
            server.process = subprocess.Popen(
                [server.command] + server.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**dict(__import__('os').environ), **server.env}
            )
            
            # Start reader thread
            server._reader_thread = threading.Thread(
                target=self._read_responses,
                args=(server,),
                daemon=True
            )
            server._reader_thread.start()
            
            # Initialize the connection
            self._send_request(server, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "suckcode", "version": "0.1.0"}
            })
            
            # Wait for initialization response
            response = self._wait_response(server, timeout=10)
            if not response or "error" in response:
                self.disconnect(server_name)
                return False
            
            # Send initialized notification
            self._send_notification(server, "notifications/initialized", {})
            
            # Discover tools
            self._discover_tools(server)
            
            # Discover resources
            self._discover_resources(server)
            
            return True
            
        except Exception as e:
            print(f"Failed to connect to MCP server {server_name}: {e}")
            self.disconnect(server_name)
            return False
    
    def disconnect(self, server_name: str):
        """Disconnect from an MCP server."""
        if server_name not in self.servers:
            return
        
        server = self.servers[server_name]
        
        # Remove tools and resources
        for tool in server.tools:
            self.all_tools.pop(f"{server_name}/{tool.name}", None)
        for resource in server.resources:
            self.all_resources.pop(resource.uri, None)
        
        # Kill process
        if server.process:
            try:
                server.process.terminate()
                server.process.wait(timeout=5)
            except:
                server.process.kill()
            server.process = None
        
        server.tools = []
        server.resources = []
    
    def disconnect_all(self):
        """Disconnect from all MCP servers."""
        for name in list(self.servers.keys()):
            self.disconnect(name)
    
    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on an MCP server."""
        if server_name not in self.servers:
            return {"error": f"Unknown server: {server_name}"}
        
        server = self.servers[server_name]
        if not server.process:
            return {"error": f"Server {server_name} not connected"}
        
        self._send_request(server, "tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        response = self._wait_response(server, timeout=60)
        if response and "result" in response:
            return response["result"]
        elif response and "error" in response:
            return {"error": response["error"]}
        return {"error": "No response from server"}
    
    def get_resource(self, uri: str) -> Optional[dict]:
        """Get a resource by URI."""
        if uri not in self.all_resources:
            return None
        
        resource = self.all_resources[uri]
        server = self.servers.get(resource.server_name)
        if not server or not server.process:
            return None
        
        self._send_request(server, "resources/read", {"uri": uri})
        response = self._wait_response(server, timeout=30)
        
        if response and "result" in response:
            return response["result"]
        return None
    
    def get_all_tools(self) -> list[MCPTool]:
        """Get all available tools from all connected servers."""
        return list(self.all_tools.values())
    
    def get_tools_schema(self) -> list[dict]:
        """Get OpenAI-compatible tool schemas for all MCP tools."""
        schemas = []
        for full_name, tool in self.all_tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": f"mcp_{tool.server_name}_{tool.name}",
                    "description": f"[MCP:{tool.server_name}] {tool.description}",
                    "parameters": tool.input_schema
                }
            })
        return schemas
    
    # ─────────────────────────────────────────────────────────────────────────
    # Private Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def _send_request(self, server: MCPServer, method: str, params: dict) -> int:
        """Send a JSON-RPC request to the server."""
        server._request_id += 1
        request_id = server._request_id
        
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        try:
            line = json.dumps(message) + "\n"
            server.process.stdin.write(line)
            server.process.stdin.flush()
        except Exception as e:
            print(f"Failed to send request: {e}")
        
        return request_id
    
    def _send_notification(self, server: MCPServer, method: str, params: dict):
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            line = json.dumps(message) + "\n"
            server.process.stdin.write(line)
            server.process.stdin.flush()
        except Exception as e:
            print(f"Failed to send notification: {e}")
    
    def _read_responses(self, server: MCPServer):
        """Read responses from server stdout (runs in thread)."""
        try:
            while server.process and server.process.poll() is None:
                line = server.process.stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line.strip())
                    server._response_queue.put(message)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
    
    def _wait_response(self, server: MCPServer, timeout: float = 30) -> Optional[dict]:
        """Wait for a response from the server."""
        try:
            return server._response_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _discover_tools(self, server: MCPServer):
        """Discover tools provided by the server."""
        self._send_request(server, "tools/list", {})
        response = self._wait_response(server, timeout=10)
        
        if response and "result" in response:
            tools = response["result"].get("tools", [])
            for t in tools:
                tool = MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {"type": "object", "properties": {}}),
                    server_name=server.name
                )
                server.tools.append(tool)
                self.all_tools[f"{server.name}/{tool.name}"] = tool
    
    def _discover_resources(self, server: MCPServer):
        """Discover resources provided by the server."""
        self._send_request(server, "resources/list", {})
        response = self._wait_response(server, timeout=10)
        
        if response and "result" in response:
            resources = response["result"].get("resources", [])
            for r in resources:
                resource = MCPResource(
                    uri=r["uri"],
                    name=r.get("name", r["uri"]),
                    description=r.get("description", ""),
                    mime_type=r.get("mimeType"),
                    server_name=server.name
                )
                server.resources.append(resource)
                self.all_resources[resource.uri] = resource

# ═══════════════════════════════════════════════════════════════════════════════
# Global MCP Client
# ═══════════════════════════════════════════════════════════════════════════════

_mcp_client: Optional[MCPClient] = None

def get_mcp_client() -> MCPClient:
    """Get or create the global MCP client."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client

def init_mcp_from_config(mcp_config: dict):
    """Initialize MCP servers from configuration."""
    client = get_mcp_client()
    
    for name, config in mcp_config.items():
        if isinstance(config, dict):
            command = config.get("command", "")
            args = config.get("args", [])
            env = config.get("env", {})
            
            if command:
                client.add_server(name, command, args, env)
                print(f"Connecting to MCP server: {name}...")
                if client.connect(name):
                    print(f"  ✓ Connected, {len(client.servers[name].tools)} tools available")
                else:
                    print(f"  ✗ Failed to connect")

def shutdown_mcp():
    """Shutdown all MCP connections."""
    global _mcp_client
    if _mcp_client:
        _mcp_client.disconnect_all()
        _mcp_client = None
