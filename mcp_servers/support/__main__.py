"""Allow `python -m mcp_servers.support`."""
from mcp_servers.support.server import _HOST, _PORT, mcp

mcp.run(transport="sse", host=_HOST, port=_PORT)
