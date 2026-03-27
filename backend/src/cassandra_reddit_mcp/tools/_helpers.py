"""Shared helpers for resolving clients."""

from __future__ import annotations

from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context

from cassandra_reddit_mcp.acl import Enforcer
from cassandra_reddit_mcp.clients.reddit import RedditClient

SERVICE_ID = "reddit-mcp"


def get_email(token: AccessToken) -> str:
    return token.claims.get("email", "")


def check_acl(enforcer: Enforcer | None, email: str, tool_name: str) -> None:
    if enforcer is None:
        return
    result = enforcer.enforce(email, SERVICE_ID, tool_name)
    if not result.allowed:
        raise ValueError(f"Access denied: {result.reason}")


def get_enforcer(ctx: Context) -> Enforcer | None:
    return ctx.lifespan_context.get("enforcer")


def resolve_reddit_client(ctx: Context) -> RedditClient:
    """Resolve the shared Reddit client (no credentials needed)."""
    client = ctx.lifespan_context.get("reddit_client")
    if client is None:
        raise ValueError("Reddit client not initialized.")
    return client
