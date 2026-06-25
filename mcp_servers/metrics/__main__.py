"""Allow `python -m mcp_servers.metrics`."""
from mcp_servers.metrics.server import _HOST, _PORT, mcp

mcp.run(transport="sse", host=_HOST, port=_PORT)
