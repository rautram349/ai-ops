"""Allow `python -m mcp_servers.support`."""
from mcp_servers.support.server import mcp, _HOST, _PORT

mcp.run(transport="sse", host=_HOST, port=_PORT)
