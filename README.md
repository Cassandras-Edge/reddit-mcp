# cassandra-reddit-mcp

Read-only Reddit MCP server. Search, browse subreddits, read posts, and pull comment threads. No writes, no DMs.

## Tools

| Tool | Purpose |
|------|---------|
| `search` | Global Reddit search (by relevance, new, top, hot) |
| `search_subreddit` | Search within a specific subreddit |
| `browse_subreddit` | Fetch hot/new/top/rising posts from a subreddit |
| `get_post` | Full post body + top-level metadata |
| `get_comments` | Comment tree for a post (flattened + threaded views) |
| `get_user` | Public profile + recent posts/comments for a user |

## Architecture

```
MCP client → reddit.cassandrasedge.com (CF Tunnel)
  → FastMCP sidecar (port 3003)
    → McpKeyAuthProvider → /keys/validate (auth service)
    → Reddit public JSON API
```

Uses Reddit's public read-only JSON API — no OAuth, no per-user credentials. Auth only gates *access to the MCP* via `mcp_` keys and per-tool ACL enforcement from the shared `cassandra-mcp-auth` library.

## Config

| Env Var | Required | Description |
|---------|----------|-------------|
| `AUTH_URL` | Yes | Auth service URL |
| `AUTH_SECRET` | Yes | Shared secret for auth service calls |
| `MCP_PORT` | No | Bind port (default `3003`) |
| `REDDIT_USER_AGENT` | No | Custom User-Agent for Reddit requests |

## Dev

```bash
cd backend
uv sync
uv run cassandra-reddit-mcp
```

## Deploy

Auto-deploys on push to main via Woodpecker CI → BuildKit → local registry → ArgoCD (`cassandra-k8s/apps/reddit-mcp/`).

Part of the [Cassandra](https://github.com/Cassandras-Edge) stack.
