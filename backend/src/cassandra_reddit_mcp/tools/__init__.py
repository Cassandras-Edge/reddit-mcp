from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from cassandra_reddit_mcp.config import Settings


def register_all(mcp: FastMCP, settings: Settings) -> None:
    from .browse import register as reg_browse

    reg_browse(mcp)
