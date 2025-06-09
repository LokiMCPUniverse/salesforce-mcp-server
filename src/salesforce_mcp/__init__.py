"""Salesforce MCP Server - Model Context Protocol server for Salesforce API integration."""

from .server import SalesforceMCPServer
from .client import SalesforceClient
from .config import SalesforceConfig, OrgConfig, RateLimitConfig
from .auth import JWTAuth, OAuth2Auth
from .exceptions import SalesforceError, AuthenticationError, RateLimitError

__version__ = "0.1.0"

__all__ = [
    "SalesforceMCPServer",
    "SalesforceClient",
    "SalesforceConfig",
    "OrgConfig",
    "RateLimitConfig",
    "JWTAuth",
    "OAuth2Auth",
    "SalesforceError",
    "AuthenticationError",
    "RateLimitError",
]