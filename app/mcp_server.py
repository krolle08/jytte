from __future__ import annotations

import logging
from mcp.server.fastmcp import FastMCP

log = logging.getLogger(__name__)

mcp = FastMCP("jytte")
mcp.settings.streamable_http_path = "/"


def attach_widgets(registry) -> None:
    for widget in registry.list():
        if not widget.expose_mcp or widget.mcp_register is None:
            continue
        try:
            widget.mcp_register(mcp, widget)
            log.info("MCP: registered tools for widget %s", widget.name)
        except Exception as e:
            log.exception("MCP: register failed for %s: %s", widget.name, e)


def mcp_asgi_app():
    return mcp.streamable_http_app()
