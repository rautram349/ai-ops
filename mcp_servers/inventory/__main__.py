"""Allow `python -m mcp_servers.inventory`."""
from mcp_servers.inventory.server import _HOST, _PORT, mcp

mcp.run(transport="sse", host=_HOST, port=_PORT)
