"""Configuration management for Salesforce MCP Server."""

import os

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    requests_per_second: float = Field(default=10.0, description="Maximum requests per second")
    burst_size: int = Field(default=20, description="Maximum burst size")
    wait_on_limit: bool = Field(default=True, description="Wait when rate limit is reached")


class OrgConfig(BaseModel):
    """Configuration for a single Salesforce org."""

    username: str | None = Field(default=None, description="Salesforce username")
    password: SecretStr | None = Field(default=None, description="Salesforce password")
    security_token: SecretStr | None = Field(default=None, description="Salesforce security token")
    domain: str = Field(default="login", description="Salesforce domain (login, test, or custom)")

    client_id: str | None = Field(default=None, description="Connected App client ID")
    client_secret: SecretStr | None = Field(default=None, description="Connected App client secret")
    redirect_uri: str | None = Field(default=None, description="OAuth redirect URI")

    api_version: str = Field(default="59.0", description="Salesforce API version")
    sandbox: bool = Field(default=False, description="Is this a sandbox org")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries")

    # Custom serializer for SecretStr handled by Pydantic automatically in v2


class SalesforceConfig(BaseSettings):
    """Main configuration for Salesforce MCP Server."""

    # Default org settings
    username: str | None = Field(default=None)
    password: SecretStr | None = Field(default=None)
    security_token: SecretStr | None = Field(default=None)
    domain: str = Field(default="login")

    # OAuth settings
    client_id: str | None = Field(default=None)
    client_secret: SecretStr | None = Field(default=None)
    redirect_uri: str | None = Field(default=None)

    # API settings
    api_version: str = Field(default="59.0")
    sandbox: bool = Field(default=False)
    timeout: int = Field(default=30)
    max_retries: int = Field(default=3)

    # Server settings
    enable_audit_log: bool = Field(default=True)
    audit_log_file: str | None = Field(default=None)

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests_per_second: float = Field(default=10.0)
    rate_limit_burst_size: int = Field(default=20)

    # Multi-org support
    default_org: str = Field(default="default")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="SALESFORCE_",
        extra="ignore",
    )

    def get_org_config(self, org_name: str | None = None) -> OrgConfig:
        """Get configuration for a specific org."""

        def _secret(value: SecretStr | None) -> str:
            return value.get_secret_value() if value else ""

        def _to_secret(raw: str | None) -> SecretStr | None:
            if raw is None or raw == "":
                return None
            return SecretStr(raw)

        if org_name and org_name != "default":
            prefix = f"SALESFORCE_{org_name.upper()}_"
            org_config = OrgConfig(
                username=os.getenv(f"{prefix}USERNAME", self.username),
                password=_to_secret(os.getenv(f"{prefix}PASSWORD", _secret(self.password))),
                security_token=_to_secret(
                    os.getenv(f"{prefix}SECURITY_TOKEN", _secret(self.security_token))
                ),
                domain=os.getenv(f"{prefix}DOMAIN", self.domain),
                client_id=os.getenv(f"{prefix}CLIENT_ID", self.client_id),
                client_secret=_to_secret(
                    os.getenv(f"{prefix}CLIENT_SECRET", _secret(self.client_secret))
                ),
                redirect_uri=os.getenv(f"{prefix}REDIRECT_URI", self.redirect_uri),
                api_version=os.getenv(f"{prefix}API_VERSION", self.api_version),
                sandbox=os.getenv(f"{prefix}SANDBOX", str(self.sandbox)).lower() == "true",
                timeout=int(os.getenv(f"{prefix}TIMEOUT", str(self.timeout))),
                max_retries=int(os.getenv(f"{prefix}MAX_RETRIES", str(self.max_retries))),
            )
        else:
            org_config = OrgConfig(
                username=self.username,
                password=self.password,
                security_token=self.security_token,
                domain=self.domain,
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                api_version=self.api_version,
                sandbox=self.sandbox,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )

        return org_config

    def get_rate_limit_config(self) -> RateLimitConfig | None:
        """Get rate limiting configuration."""
        if not self.rate_limit_enabled:
            return None

        return RateLimitConfig(
            requests_per_second=self.rate_limit_requests_per_second,
            burst_size=self.rate_limit_burst_size,
            wait_on_limit=True
        )

    def validate_config(self, require_credentials: bool = False) -> bool:
        """Validate the configuration.

        Args:
            require_credentials: If True, raise when neither username/password nor
                OAuth client credentials are set. By default, an MCP server may
                start without default credentials and authenticate per-org later.
        """
        has_basic_auth = all([self.username, self.password])
        has_oauth = all([self.client_id, self.client_secret])

        if require_credentials and not (has_basic_auth or has_oauth):
            raise ValueError(
                "Invalid configuration: Either username/password or OAuth credentials required"
            )

        return True
