"""FastMCP server for Cassandra Reddit MCP — subreddit browsing, search, posts, comments.

Uses public .json endpoints — no Reddit API credentials required.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP

from cassandra_reddit_mcp.auth import McpKeyAuthProvider, build_auth
from cassandra_reddit_mcp.clients.reddit import RedditClient
from cassandra_reddit_mcp.config import Settings

logger = logging.getLogger(__name__)

SERVICE_ID = "reddit-mcp"


def create_mcp_server(settings: Settings) -> FastMCP:
    """Create and configure the FastMCP server with auth and all tools."""

    auth_provider = None
    mcp_key_provider = None
    if settings.auth_url and settings.auth_secret:
        if (
            settings.workos_client_id
            and settings.workos_client_secret
            and settings.workos_authkit_domain
            and settings.base_url
        ):
            auth_provider, mcp_key_provider = build_auth(
                acl_url=settings.auth_url,
                acl_secret=settings.auth_secret,
                service_id=SERVICE_ID,
                base_url=settings.base_url,
                workos_client_id=settings.workos_client_id,
                workos_client_secret=settings.workos_client_secret,
                workos_authkit_domain=settings.workos_authkit_domain,
            )
        else:
            mcp_key_provider = McpKeyAuthProvider(
                acl_url=settings.auth_url,
                acl_secret=settings.auth_secret,
                service_id=SERVICE_ID,
            )
            auth_provider = mcp_key_provider

    # Load ACL enforcer from bundled acl.yaml
    acl_path = Path(settings.auth_yaml_path)
    enforcer = None
    if acl_path.exists():
        from cassandra_reddit_mcp.acl import load_enforcer  # noqa: PLC0415

        enforcer = load_enforcer(acl_path)

    # Reddit client — no credentials needed, uses public .json endpoints
    reddit_client = RedditClient(user_agent=settings.reddit_user_agent)

    @asynccontextmanager
    async def lifespan(server):
        yield {
            "reddit_client": reddit_client,
            "enforcer": enforcer,
        }
        await reddit_client.close()
        if mcp_key_provider is not None:
            mcp_key_provider.close()

    mcp_kwargs: dict = {
        "name": "Cassandra Reddit",
        "instructions": (
            "Reddit browsing server for research and discourse analysis. "
            "Use search to find posts across Reddit or within a subreddit. "
            "Use get_subreddit to browse a community's posts (hot/new/top/rising). "
            "Use get_post to read a post with its full comment thread. "
            "Use get_comment_thread to drill into a specific comment chain. "
            "All tools are read-only and idempotent. Results are cached — "
            "re-reading the same post or thread is free."
        ),
        "lifespan": lifespan,
    }
    if auth_provider:
        mcp_kwargs["auth"] = auth_provider

    mcp = FastMCP(**mcp_kwargs)

    # Health check
    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request):  # noqa: ANN001, ARG001
        from starlette.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse({"ok": True, "service": "cassandra-reddit-mcp"})

    # Register all tool modules
    from cassandra_reddit_mcp.tools import register_all  # noqa: PLC0415

    register_all(mcp, settings)

    return mcp
