"""Allow `python -m mcp_servers.inventory`."""
from mcp_servers.inventory.server import mcp, _HOST, _PORT

mcp.run(transport="sse", host=_HOST, port=_PORT)
