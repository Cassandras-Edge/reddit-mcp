"""FastMCP server for Cassandra Reddit MCP — subreddit browsing, search, posts, comments.

Uses public .json endpoints — no Reddit API credentials required.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from cassandra_mcp_auth import AclMiddleware, DiscoveryTransform
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
            and settings.workos_authkit_domain
            and settings.base_url
        ):
            auth_provider, mcp_key_provider = build_auth(
                acl_url=settings.auth_url,
                acl_secret=settings.auth_secret,
                service_id=SERVICE_ID,
                base_url=settings.base_url,
                workos_client_id=settings.workos_client_id,
                workos_authkit_domain=settings.workos_authkit_domain,
            )
        else:
            mcp_key_provider = McpKeyAuthProvider(
                acl_url=settings.auth_url,
                acl_secret=settings.auth_secret,
                service_id=SERVICE_ID,
            )
            auth_provider = mcp_key_provider

    reddit_client = RedditClient(user_agent=settings.reddit_user_agent)

    # Set fallback so tools work even without lifespan (gateway embedding)
    from cassandra_reddit_mcp.tools._helpers import set_fallback_client
    set_fallback_client(reddit_client)

    @asynccontextmanager
    async def lifespan(server):
        yield {
            "reddit_client": reddit_client,
        }
        await reddit_client.close()
        if mcp_key_provider is not None:
            mcp_key_provider.close()

    acl_mw = AclMiddleware(service_id=SERVICE_ID, acl_path=settings.auth_yaml_path)

    mcp_kwargs: dict = {
        "name": "Cassandra Reddit",
        "instructions": (
            "# Cassandra Reddit\n\n"
            "Use this when the user wants to know what a community thinks. Reddit is "
            "where people discuss things in depth — product reviews, technical debates, "
            "industry drama, niche topics.\n\n"
            "Think of this server when the user asks about:\n"
            "- What people are saying about something on Reddit\n"
            "- Community sentiment or opinions\n"
            "- Browsing a subreddit's current posts\n"
            "- Reading a specific discussion thread\n\n"
            "Uses public .json endpoints — no API credentials, results cached. "
            "All tools are read-only.\n\n"
            "## How this works\n\n"
            "This is a DISCOVERY server — it tells you what tools exist and how to "
            "call them. To actually execute a tool, use the cassandra-gateway server.\n\n"
            "### Step 1: Find tools (this server)\n"
            "Call `cass_reddit_search` to look up tools and get their full parameter schemas.\n\n"
            "```\n"
            "cass_reddit_search(\n"
            "  query: str,           # what you're looking for, e.g. 'browse subreddit'\n"
            "  tags: list[str]=None, # optional tag filter\n"
            "  detail: str='full',   # 'brief' for names only, 'detailed' for markdown, 'full' for JSON schemas\n"
            "  limit: int=None       # max results\n"
            ")\n"
            "```\n\n"
            "### Step 2: Execute tools (cassandra-gateway server)\n"
            "Take the tool name and params from step 1, then call `cass_gateway_run` "
            "on the cassandra-gateway server:\n\n"
            "```\n"
            "cass_gateway_run(code=\"return await call_tool('get_subreddit', {'subreddit': 'wallstreetbets'})\")\n"
            "```"
        ),
        "lifespan": lifespan,
        "middleware": [acl_mw] if acl_mw._enabled else [],  # noqa: SLF001
    }
    if settings.code_mode:
        mcp_kwargs["transforms"] = [DiscoveryTransform(service_id=SERVICE_ID)]
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
