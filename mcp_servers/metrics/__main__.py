"""Allow `python -m mcp_servers.metrics`."""
from mcp_servers.metrics.server import mcp, _HOST, _PORT

mcp.run(transport="sse", host=_HOST, port=_PORT)
