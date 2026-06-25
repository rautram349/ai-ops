"""Centralised environment configuration for all MCP servers.

Import from this module instead of calling ``os.environ.get`` directly in
each server.  ``load_dotenv()`` is called once here so individual servers
do not need to call it themselves.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from backend.constants import (
    DATABASE_URL_SYNC_DEFAULT,
    MCP_DEFAULT_HOST,
    MCP_INVENTORY_DEFAULT_PORT,
    MCP_MARKETING_DEFAULT_PORT,
    MCP_METRICS_DEFAULT_PORT,
    MCP_SUPPORT_DEFAULT_PORT,
)

load_dotenv()

DATABASE_URL_SYNC: str = os.environ.get("DATABASE_URL_SYNC", DATABASE_URL_SYNC_DEFAULT)

MCP_METRICS_HOST:   str = os.environ.get("MCP_METRICS_HOST",   MCP_DEFAULT_HOST)
MCP_METRICS_PORT:   int = int(os.environ.get("MCP_METRICS_PORT",   str(MCP_METRICS_DEFAULT_PORT)))

MCP_INVENTORY_HOST: str = os.environ.get("MCP_INVENTORY_HOST", MCP_DEFAULT_HOST)
MCP_INVENTORY_PORT: int = int(os.environ.get("MCP_INVENTORY_PORT", str(MCP_INVENTORY_DEFAULT_PORT)))

MCP_MARKETING_HOST: str = os.environ.get("MCP_MARKETING_HOST", MCP_DEFAULT_HOST)
MCP_MARKETING_PORT: int = int(os.environ.get("MCP_MARKETING_PORT", str(MCP_MARKETING_DEFAULT_PORT)))

MCP_SUPPORT_HOST:   str = os.environ.get("MCP_SUPPORT_HOST",   MCP_DEFAULT_HOST)
MCP_SUPPORT_PORT:   int = int(os.environ.get("MCP_SUPPORT_PORT",   str(MCP_SUPPORT_DEFAULT_PORT)))
