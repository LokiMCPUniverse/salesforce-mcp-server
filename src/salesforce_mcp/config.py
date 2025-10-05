"""Configuration management for Salesforce MCP Server."""

from typing import Optional
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings
import os


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""
    
    requests_per_second: float = Field(default=10.0, description="Maximum requests per second")
    burst_size: int = Field(default=20, description="Maximum burst size")
    wait_on_limit: bool = Field(default=True, description="Wait when rate limit is reached")


class OrgConfig(BaseModel):
    """Configuration for a single Salesforce org."""
    
    username: Optional[str] = Field(default=None, description="Salesforce username")
    password: Optional[SecretStr] = Field(default=None, description="Salesforce password")
    security_token: Optional[SecretStr] = Field(default=None, description="Salesforce security token")
    domain: str = Field(default="login", description="Salesforce domain (login, test, or custom)")
    
    client_id: Optional[str] = Field(default=None, description="Connected App client ID")
    client_secret: Optional[SecretStr] = Field(default=None, description="Connected App client secret")
    redirect_uri: Optional[str] = Field(default=None, description="OAuth redirect URI")
    
    api_version: str = Field(default="59.0", description="Salesforce API version")
    sandbox: bool = Field(default=False, description="Is this a sandbox org")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries")
    
    # Custom serializer for SecretStr handled by Pydantic automatically in v2


class SalesforceConfig(BaseSettings):
    """Main configuration for Salesforce MCP Server."""
    
    # Default org settings
    username: Optional[str] = Field(default=None)
    password: Optional[SecretStr] = Field(default=None)
    security_token: Optional[SecretStr] = Field(default=None)
    domain: str = Field(default="login")
    
    # OAuth settings
    client_id: Optional[str] = Field(default=None)
    client_secret: Optional[SecretStr] = Field(default=None)
    redirect_uri: Optional[str] = Field(default=None)
    
    # API settings
    api_version: str = Field(default="59.0")
    sandbox: bool = Field(default=False)
    timeout: int = Field(default=30)
    max_retries: int = Field(default=3)
    
    # Server settings
    enable_audit_log: bool = Field(default=True)
    audit_log_file: Optional[str] = Field(default=None)
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests_per_second: float = Field(default=10.0)
    rate_limit_burst_size: int = Field(default=20)
    
    # Multi-org support
    default_org: str = Field(default="default")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "env_prefix": "SALESFORCE_"
    }
    
    def get_org_config(self, org_name: Optional[str] = None) -> OrgConfig:
        """Get configuration for a specific org."""
        if org_name and org_name != "default":
            # Look for org-specific environment variables
            prefix = f"SALESFORCE_{org_name.upper()}_"
            org_config = OrgConfig(
                username=os.getenv(f"{prefix}USERNAME", self.username),
                password=SecretStr(os.getenv(f"{prefix}PASSWORD", self.password.get_secret_value() if self.password else "")),
                security_token=SecretStr(os.getenv(f"{prefix}SECURITY_TOKEN", self.security_token.get_secret_value() if self.security_token else "")),
                domain=os.getenv(f"{prefix}DOMAIN", self.domain),
                client_id=os.getenv(f"{prefix}CLIENT_ID", self.client_id),
                client_secret=SecretStr(os.getenv(f"{prefix}CLIENT_SECRET", self.client_secret.get_secret_value() if self.client_secret else "")),
                redirect_uri=os.getenv(f"{prefix}REDIRECT_URI", self.redirect_uri),
                api_version=os.getenv(f"{prefix}API_VERSION", self.api_version),
                sandbox=os.getenv(f"{prefix}SANDBOX", str(self.sandbox)).lower() == "true",
                timeout=int(os.getenv(f"{prefix}TIMEOUT", str(self.timeout))),
                max_retries=int(os.getenv(f"{prefix}MAX_RETRIES", str(self.max_retries)))
            )
        else:
            # Use default configuration
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
                max_retries=self.max_retries
            )
        
        return org_config
    
    def get_rate_limit_config(self) -> RateLimitConfig:
        """Get rate limiting configuration."""
        if not self.rate_limit_enabled:
            return None
        
        return RateLimitConfig(
            requests_per_second=self.rate_limit_requests_per_second,
            burst_size=self.rate_limit_burst_size,
            wait_on_limit=True
        )
    
    def validate_config(self) -> bool:
        """Validate the configuration."""
        # Check if we have either username/password or OAuth credentials
        has_basic_auth = all([self.username, self.password])
        has_oauth = all([self.client_id, self.client_secret])
        
        if not (has_basic_auth or has_oauth):
            raise ValueError(
                "Invalid configuration: Either username/password or OAuth credentials required"
            )
        
        return True