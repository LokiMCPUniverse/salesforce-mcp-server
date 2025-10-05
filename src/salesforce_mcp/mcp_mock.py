"""Mock MCP module for testing and development."""

from typing import Dict, Any
from dataclasses import dataclass
import asyncio


@dataclass
class Tool:
    """Mock Tool class."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class TextContent:
    """Mock TextContent class."""
    type: str
    text: str


@dataclass
class NotificationOptions:
    """Mock NotificationOptions class."""
    pass


@dataclass
class InitializationOptions:
    """Mock InitializationOptions class."""
    server_name: str
    server_version: str
    capabilities: Dict[str, Any]


class Server:
    """Mock Server class."""
    
    def __init__(self, name: str):
        self.name = name
        self._tools = []
        self._tool_handlers = {}
    
    def list_tools(self):
        """Decorator for list tools handler."""
        def decorator(func):
            self._list_tools_handler = func
            return func
        return decorator
    
    def call_tool(self):
        """Decorator for call tool handler."""
        def decorator(func):
            self._call_tool_handler = func
            return func
        return decorator
    
    def get_capabilities(self, notification_options: Any, experimental_capabilities: Dict) -> Dict[str, Any]:
        """Get server capabilities."""
        return {
            "tools": True,
            "notifications": False,
            "experimental": experimental_capabilities
        }
    
    async def run(self, read_stream, write_stream, init_options):
        """Run the server."""
        await asyncio.sleep(0)  # Placeholder


class StdioServer:
    """Mock stdio server context manager."""
    
    async def __aenter__(self):
        """Enter context."""
        read_stream = None
        write_stream = None
        return read_stream, write_stream
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        pass


def stdio_server():
    """Create stdio server."""
    return StdioServer()