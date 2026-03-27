"""All Reddit navigation tools — search, subreddit, post, comment thread."""

from __future__ import annotations

from typing import Literal, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentAccessToken
from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from cassandra_reddit_mcp.tools._helpers import (
    check_acl, get_email, get_enforcer, resolve_reddit_client,
)


def register(mcp: FastMCP) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @mcp.tool(annotations=_ro)
    async def search(
        query: str,
        ctx: Context,
        subreddit: Optional[str] = None,
        sort: Literal["relevance", "hot", "top", "new", "comments"] = "relevance",
        time_filter: Literal["all", "day", "hour", "month", "week", "year"] = "all",
        limit: int = 25,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Search Reddit for posts matching a query.

        Good starting point for exploring a topic. Returns post titles, scores,
        comment counts, and permalinks. Can search all of Reddit or within a
        specific subreddit.

        Args:
            query: Search query string.
            subreddit: Restrict to a subreddit (e.g. 'stocks'). Omit to search all.
            sort: Sort order — relevance, hot, top, new, comments (default: relevance).
            time_filter: Time window — all, day, hour, month, week, year (default: all).
            limit: Max results (1-100, default 25).
        """
        check_acl(get_enforcer(ctx), get_email(token), "search")
        client = resolve_reddit_client(ctx)
        limit = max(1, min(limit, 100))
        try:
            data = await client.search(
                query, subreddit=subreddit, sort=sort,
                time_filter=time_filter, limit=limit,
            )
            return {
                "query": query,
                "subreddit": subreddit,
                "sort": sort,
                "count": len(data["posts"]),
                **data,
            }
        except httpx.HTTPStatusError as exc:
            return {"error": "Reddit search failed", "status": exc.response.status_code}
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return {"error": "Reddit search failed", "detail": str(exc)}

    @mcp.tool(annotations=_ro)
    async def get_subreddit(
        subreddit: str,
        ctx: Context,
        sort: Literal["hot", "new", "top", "rising", "controversial"] = "hot",
        time_filter: Literal["all", "day", "hour", "month", "week", "year"] = "day",
        limit: int = 25,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Browse a subreddit's posts.

        Returns posts sorted by the chosen order. Use this to see what a
        community is talking about right now.

        Args:
            subreddit: Subreddit name without r/ (e.g. 'wallstreetbets', 'technology').
            sort: Sort — hot, new, top, rising, controversial (default: hot).
            time_filter: For top/controversial — all, day, hour, month, week, year
                (default: day). Ignored for hot/new/rising.
            limit: Max posts (1-100, default 25).
        """
        check_acl(get_enforcer(ctx), get_email(token), "get_subreddit")
        client = resolve_reddit_client(ctx)
        subreddit = subreddit.removeprefix("r/").strip()
        limit = max(1, min(limit, 100))
        try:
            return await client.get_subreddit(
                subreddit, sort=sort, time_filter=time_filter, limit=limit,
            )
        except httpx.HTTPStatusError as exc:
            return {"error": "Failed to fetch subreddit", "status": exc.response.status_code}
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return {"error": "Failed to fetch subreddit", "detail": str(exc)}

    @mcp.tool(annotations=_ro)
    async def get_post(
        post_id: str,
        ctx: Context,
        comment_sort: Literal["confidence", "top", "new", "controversial", "old"] = "confidence",
        comment_depth: int = 4,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Read a Reddit post and its entire comment thread.

        Downloads the full post and comment tree in a single request. Comments
        are nested with replies. Results are cached so re-reading is free.

        Args:
            post_id: Post ID (e.g. 'abc123') or full Reddit URL.
            comment_sort: Sort comments — confidence (best), top, new,
                controversial, old (default: confidence).
            comment_depth: Max reply nesting depth (1-10, default 4).
        """
        check_acl(get_enforcer(ctx), get_email(token), "get_post")
        client = resolve_reddit_client(ctx)
        comment_depth = max(1, min(comment_depth, 10))
        try:
            return await client.get_post(
                post_id,
                comment_sort=comment_sort,
                comment_depth=comment_depth,
            )
        except httpx.HTTPStatusError as exc:
            return {"error": "Failed to fetch post", "status": exc.response.status_code}
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return {"error": "Failed to fetch post", "detail": str(exc)}

    @mcp.tool(annotations=_ro)
    async def get_comment_thread(
        comment_id: str,
        ctx: Context,
        depth: int = 6,
        context: int = 2,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Drill into a specific comment and its reply chain.

        Use this to follow a conversation deeper — expands the full reply tree
        below a comment and shows parent comments for context. Accepts a
        comment ID or permalink URL.

        Args:
            comment_id: Comment ID (e.g. 'kx1234') or permalink URL.
            depth: How deep to traverse replies (1-10, default 6).
            context: Number of parent comments to include above (0-8, default 2).
        """
        check_acl(get_enforcer(ctx), get_email(token), "get_comment_thread")
        client = resolve_reddit_client(ctx)
        depth = max(1, min(depth, 10))
        context = max(0, min(context, 8))
        try:
            return await client.get_comment_thread(
                comment_id, depth=depth, context=context,
            )
        except httpx.HTTPStatusError as exc:
            return {"error": "Failed to fetch comment thread", "status": exc.response.status_code}
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return {"error": "Failed to fetch comment thread", "detail": str(exc)}
