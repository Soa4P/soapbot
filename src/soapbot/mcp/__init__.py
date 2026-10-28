"""MCP (Model Context Protocol) client: external tools on the same tool table."""

from soapbot.mcp.client import McpClient, McpError, McpManager, McpServer, McpTool
from soapbot.mcp.config import McpConfigError, load_config

__all__ = [
    "McpClient",
    "McpConfigError",
    "McpError",
    "McpManager",
    "McpServer",
    "McpTool",
    "load_config",
]
