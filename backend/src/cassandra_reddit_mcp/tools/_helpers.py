"""Shared helpers for resolving clients."""

from __future__ import annotations

from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context

from cassandra_reddit_mcp.clients.reddit import RedditClient

# Module-level client set by create_mcp_server — available even without lifespan
_fallback_client: RedditClient | None = None


def set_fallback_client(client: RedditClient) -> None:
    global _fallback_client
    _fallback_client = client


def get_email(token: AccessToken | None) -> str:
    if token is None:
        return ""
    return token.claims.get("email", "")


def resolve_reddit_client(ctx: Context) -> RedditClient:
    """Resolve the shared Reddit client — lifespan context or fallback."""
    if ctx.lifespan_context is not None:
        client = ctx.lifespan_context.get("reddit_client")
        if client is not None:
            return client
    if _fallback_client is not None:
        return _fallback_client
    raise ValueError("Reddit client not initialized.")
