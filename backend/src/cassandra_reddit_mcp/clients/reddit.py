"""Reddit client using public .json endpoints — no API key required.

Hits old.reddit.com/{path}.json which returns the same data Reddit renders.
One request fetches an entire post with all comments. Results are cached
with a TTL so repeated navigation doesn't burn rate limit.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://old.reddit.com"
DEFAULT_USER_AGENT = "cassandra-reddit-mcp/0.1.0 (research; read-only)"
CACHE_TTL_SECONDS = 300  # 5 min


# ── Cache ────────────────────────────────────────────────────────────────


class _CacheEntry:
    __slots__ = ("data", "created_at")

    def __init__(self, data: Any) -> None:
        self.data = data
        self.created_at = time.monotonic()

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > CACHE_TTL_SECONDS


class _Cache:
    """Simple in-memory TTL cache keyed by URL."""

    def __init__(self, max_size: int = 200) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._store[key]
            return None
        return entry.data

    def set(self, key: str, data: Any) -> None:
        if len(self._store) >= self._max_size:
            self._evict()
        self._store[key] = _CacheEntry(data)

    def _evict(self) -> None:
        expired = [k for k, v in self._store.items() if v.is_expired()]
        for k in expired:
            del self._store[k]
        # If still over, drop oldest
        if len(self._store) >= self._max_size:
            oldest = min(self._store, key=lambda k: self._store[k].created_at)
            del self._store[oldest]


# ── Formatting ───────────────────────────────────────────────────────────


def _format_post(data: dict) -> dict[str, Any]:
    """Extract useful fields from a Reddit listing post (t3)."""
    d = data.get("data", data)
    result: dict[str, Any] = {
        "id": d.get("id"),
        "title": d.get("title"),
        "author": d.get("author", "[deleted]"),
        "subreddit": d.get("subreddit"),
        "permalink": f"https://reddit.com{d['permalink']}" if d.get("permalink") else None,
        "score": d.get("score"),
        "upvote_ratio": d.get("upvote_ratio"),
        "num_comments": d.get("num_comments"),
        "created_utc": d.get("created_utc"),
        "link_flair_text": d.get("link_flair_text"),
        "stickied": d.get("stickied"),
    }
    if d.get("is_self"):
        selftext = d.get("selftext", "")
        result["selftext"] = selftext[:4000] if selftext else None
    else:
        result["url"] = d.get("url")
    return result


def _format_comment(data: dict, *, max_depth: int, current_depth: int = 0) -> dict[str, Any]:
    """Recursively format a comment (t1) and its replies."""
    d = data.get("data", data)
    comment: dict[str, Any] = {
        "id": d.get("id"),
        "author": d.get("author", "[deleted]"),
        "body": (d.get("body") or "[removed]")[:4000],
        "score": d.get("score"),
        "created_utc": d.get("created_utc"),
        "depth": current_depth,
        "is_submitter": d.get("is_submitter", False),
        "permalink": f"https://reddit.com{d['permalink']}" if d.get("permalink") else None,
    }

    # Recurse into replies
    if current_depth < max_depth:
        replies_listing = d.get("replies")
        if isinstance(replies_listing, dict):
            children = replies_listing.get("data", {}).get("children", [])
            replies = []
            for child in children:
                if child.get("kind") == "t1":
                    replies.append(
                        _format_comment(child, max_depth=max_depth, current_depth=current_depth + 1)
                    )
            if replies:
                comment["replies"] = replies

    return comment


# ── Client ───────────────────────────────────────────────────────────────


class RedditClient:
    """Reddit client using public .json endpoints with caching."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            timeout=15,
        )
        self._cache = _Cache()

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, params: dict | None = None) -> Any:
        """Fetch a .json endpoint, using cache when available."""
        # Build cache key from path + sorted params
        cache_key = path
        if params:
            sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            cache_key = f"{path}?{sorted_params}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        data = resp.json()
        self._cache.set(cache_key, data)
        return data

    # ── Search ──────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        subreddit: str | None = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
    ) -> dict[str, Any]:
        if subreddit:
            path = f"/r/{subreddit}/search.json"
        else:
            path = "/search.json"

        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 100),
            "restrict_sr": "1" if subreddit else "0",
            "type": "link",
        }
        data = await self._get_json(path, params)

        posts = []
        for child in data.get("data", {}).get("children", []):
            if child.get("kind") == "t3":
                posts.append(_format_post(child))

        return {"posts": posts, "after": data.get("data", {}).get("after")}

    # ── Subreddit browsing ──────────────────────────────────────────

    async def get_subreddit(
        self,
        subreddit: str,
        *,
        sort: str = "hot",
        time_filter: str = "day",
        limit: int = 25,
    ) -> dict[str, Any]:
        path = f"/r/{subreddit}/{sort}.json"
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if sort in ("top", "controversial"):
            params["t"] = time_filter

        data = await self._get_json(path, params)

        posts = []
        for child in data.get("data", {}).get("children", []):
            if child.get("kind") == "t3":
                posts.append(_format_post(child))

        return {"subreddit": subreddit, "sort": sort, "posts": posts}

    async def get_subreddit_about(self, subreddit: str) -> dict[str, Any]:
        data = await self._get_json(f"/r/{subreddit}/about.json")
        d = data.get("data", {})
        return {
            "name": d.get("display_name"),
            "title": d.get("title"),
            "description": (d.get("public_description") or "")[:500],
            "long_description": (d.get("description") or "")[:2000],
            "subscribers": d.get("subscribers"),
            "active_users": d.get("accounts_active"),
            "created_utc": d.get("created_utc"),
            "over18": d.get("over18"),
        }

    # ── Post + comments (single request) ────────────────────────────

    async def get_post(
        self,
        post_id: str,
        *,
        comment_sort: str = "confidence",
        comment_depth: int = 4,
        comment_limit: int = 200,
    ) -> dict[str, Any]:
        """Fetch a post and its entire comment tree in one request.

        Reddit returns [post_listing, comment_listing] for a single .json call.
        """
        # Handle full URLs
        if post_id.startswith(("http://", "https://")):
            # Extract path from URL
            from urllib.parse import urlparse  # noqa: PLC0415

            parsed = urlparse(post_id)
            path = parsed.path.rstrip("/") + ".json"
        else:
            post_id = post_id.lstrip("t3_")
            path = f"/comments/{post_id}.json"

        params: dict[str, Any] = {
            "sort": comment_sort,
            "depth": min(comment_depth, 10),
            "limit": min(comment_limit, 500),
        }
        data = await self._get_json(path, params)

        # Reddit returns an array: [post_listing, comments_listing]
        if not isinstance(data, list) or len(data) < 2:
            return {"error": "Unexpected response format"}

        # Post
        post_children = data[0].get("data", {}).get("children", [])
        post = _format_post(post_children[0]) if post_children else {}

        # Comments
        comment_children = data[1].get("data", {}).get("children", [])
        comments = []
        for child in comment_children:
            if child.get("kind") == "t1":
                comments.append(
                    _format_comment(child, max_depth=comment_depth)
                )

        return {
            "post": post,
            "comments": comments,
            "meta": {
                "comment_sort": comment_sort,
                "comments_returned": len(comments),
                "total_comments": post.get("num_comments"),
            },
        }

    # ── Comment thread drill-down ────────────────────────────────────

    async def get_comment_thread(
        self,
        comment_id: str,
        *,
        depth: int = 6,
        context: int = 2,
    ) -> dict[str, Any]:
        """Fetch a specific comment thread with parent context.

        Uses the ?comment={id}&context={n} query params which Reddit supports
        natively — returns the comment with N parents above it and full
        reply tree below.
        """
        # Handle permalink URLs
        if comment_id.startswith(("http://", "https://")):
            from urllib.parse import urlparse  # noqa: PLC0415

            parsed = urlparse(comment_id)
            path = parsed.path.rstrip("/") + ".json"
            params: dict[str, Any] = {"depth": min(depth, 10), "context": min(context, 8)}
        else:
            comment_id = comment_id.lstrip("t1_")
            # We need the post ID to build the URL — use the comment permalink endpoint
            path = f"/api/info.json"
            info_data = await self._get_json(path, {"id": f"t1_{comment_id}"})
            children = info_data.get("data", {}).get("children", [])
            if not children:
                return {"error": "Comment not found", "comment_id": comment_id}

            comment_data = children[0].get("data", {})
            permalink = comment_data.get("permalink", "")
            if not permalink:
                return {"error": "No permalink for comment", "comment_id": comment_id}

            path = permalink.rstrip("/") + ".json"
            params = {"depth": min(depth, 10), "context": min(context, 8)}

        data = await self._get_json(path, params)

        if not isinstance(data, list) or len(data) < 2:
            return {"error": "Unexpected response format"}

        # First listing has the post + parent context
        context_posts = data[0].get("data", {}).get("children", [])
        parents: list[dict[str, Any]] = []
        for child in context_posts:
            if child.get("kind") == "t3":
                parents.append({"type": "post", **_format_post(child)})
            elif child.get("kind") == "t1":
                parents.append(_format_comment(child, max_depth=0))

        # Second listing is the target comment with its reply tree
        comment_children = data[1].get("data", {}).get("children", [])
        thread = None
        for child in comment_children:
            if child.get("kind") == "t1":
                thread = _format_comment(child, max_depth=depth)
                break

        return {
            "context": parents,
            "comment": thread,
            "meta": {
                "comment_id": comment_id,
                "depth_limit": depth,
                "context_parents": len(parents),
            },
        }
