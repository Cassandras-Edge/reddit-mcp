"""Settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    # Reddit (no API credentials needed — uses public .json endpoints)
    reddit_user_agent: str

    # Auth (ACL service)
    auth_url: str
    auth_secret: str
    auth_yaml_path: str

    # WorkOS OAuth
    workos_client_id: str
    workos_client_secret: str
    workos_authkit_domain: str
    base_url: str

    # Server
    host: str
    mcp_port: int


def load_settings() -> Settings:
    return Settings(
        reddit_user_agent=os.environ.get("REDDIT_USER_AGENT", "cassandra-reddit-mcp/0.1.0"),
        auth_url=os.environ.get("AUTH_URL", ""),
        auth_secret=os.environ.get("AUTH_SECRET", ""),
        auth_yaml_path=os.environ.get("AUTH_YAML_PATH", "/app/acl.yaml"),
        workos_client_id=os.environ.get("WORKOS_CLIENT_ID", ""),
        workos_client_secret=os.environ.get("WORKOS_CLIENT_SECRET", ""),
        workos_authkit_domain=os.environ.get("WORKOS_AUTHKIT_DOMAIN", ""),
        base_url=os.environ.get("BASE_URL", ""),
        host=os.environ.get("HOST", "0.0.0.0"),
        mcp_port=int(os.environ.get("MCP_PORT", "3004")),
    )
