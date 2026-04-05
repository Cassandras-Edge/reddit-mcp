"""Shared helpers for resolving clients."""

from __future__ import annotations

from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context

from cassandra_reddit_mcp.clients.reddit import RedditClient


def get_email(token: AccessToken) -> str:
    return token.claims.get("email", "")


def resolve_reddit_client(ctx: Context) -> RedditClient:
    """Resolve the shared Reddit client (no credentials needed)."""
    client = ctx.lifespan_context.get("reddit_client")
    if client is None:
        raise ValueError("Reddit client not initialized.")
    return client
