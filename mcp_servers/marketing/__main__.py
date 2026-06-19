"""Allow `python -m mcp_servers.marketing`."""
from mcp_servers.marketing.server import mcp, _HOST, _PORT

mcp.run(transport="sse", host=_HOST, port=_PORT)
