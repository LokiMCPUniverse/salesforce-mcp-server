"""Salesforce MCP Server - Model Context Protocol server for Salesforce API integration."""

from .auth import JWTAuth, OAuth2Auth, UsernamePasswordAuth
from .client import SalesforceClient
from .config import OrgConfig, RateLimitConfig, SalesforceConfig
from .exceptions import AuthenticationError, RateLimitError, SalesforceError
from .server import AppContext, mcp

__version__ = "0.2.0"

__all__ = [
    "AppContext",
    "AuthenticationError",
    "JWTAuth",
    "OAuth2Auth",
    "OrgConfig",
    "RateLimitConfig",
    "RateLimitError",
    "SalesforceClient",
    "SalesforceConfig",
    "SalesforceError",
    "UsernamePasswordAuth",
    "mcp",
]
