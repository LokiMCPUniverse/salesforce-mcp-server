"""Authentication handlers for Salesforce MCP Server."""

import json
import time
import jwt
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from .exceptions import AuthenticationError


class AuthBase:
    """Base authentication class."""
    
    def __init__(self):
        self.access_token: Optional[str] = None
        self.instance_url: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
    
    def is_token_valid(self) -> bool:
        """Check if the current token is still valid."""
        if not self.access_token or not self.token_expiry:
            return False
        return datetime.utcnow() < self.token_expiry
    
    async def get_headers(self) -> Dict[str, str]:
        """Get authentication headers."""
        if not self.is_token_valid():
            await self.authenticate()
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def authenticate(self) -> None:
        """Authenticate with Salesforce (to be implemented by subclasses)."""
        raise NotImplementedError


class UsernamePasswordAuth(AuthBase):
    """Username-password authentication flow."""
    
    def __init__(
        self,
        username: str,
        password: str,
        security_token: str = "",
        domain: str = "login",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        super().__init__()
        self.username = username
        self.password = password
        self.security_token = security_token
        self.domain = domain
        self.client_id = client_id
        self.client_secret = client_secret
    
    async def authenticate(self) -> None:
        """Authenticate using username and password."""
        url = f"https://{self.domain}.salesforce.com/services/oauth2/token"
        
        data = {
            "grant_type": "password",
            "username": self.username,
            "password": f"{self.password}{self.security_token}"
        }
        
        if self.client_id and self.client_secret:
            data["client_id"] = self.client_id
            data["client_secret"] = self.client_secret
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=data)
                response.raise_for_status()
                
                result = response.json()
                self.access_token = result["access_token"]
                self.instance_url = result["instance_url"]
                # Tokens typically last 2 hours
                self.token_expiry = datetime.utcnow() + timedelta(hours=2)
                
            except httpx.HTTPStatusError as e:
                error_data = e.response.json() if e.response.content else {}
                raise AuthenticationError(
                    f"Authentication failed: {error_data.get('error_description', str(e))}",
                    auth_type="username_password"
                )


class OAuth2Auth(AuthBase):
    """OAuth 2.0 Web Server Flow authentication."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        domain: str = "login",
        refresh_token: Optional[str] = None
    ):
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.domain = domain
        self.refresh_token = refresh_token
        self.authorization_code: Optional[str] = None
    
    def get_authorization_url(self) -> str:
        """Get the URL for user authorization."""
        base_url = f"https://{self.domain}.salesforce.com/services/oauth2/authorize"
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "full refresh_token"
        }
        return f"{base_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    
    def set_authorization_code(self, code: str) -> None:
        """Set the authorization code received from the callback."""
        self.authorization_code = code
    
    async def authenticate(self) -> None:
        """Authenticate using OAuth 2.0."""
        if self.refresh_token:
            await self._refresh_access_token()
        elif self.authorization_code:
            await self._exchange_code_for_token()
        else:
            raise AuthenticationError(
                "No refresh token or authorization code available",
                auth_type="oauth2"
            )
    
    async def _exchange_code_for_token(self) -> None:
        """Exchange authorization code for access token."""
        url = f"https://{self.domain}.salesforce.com/services/oauth2/token"
        
        data = {
            "grant_type": "authorization_code",
            "code": self.authorization_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=data)
                response.raise_for_status()
                
                result = response.json()
                self.access_token = result["access_token"]
                self.instance_url = result["instance_url"]
                self.refresh_token = result.get("refresh_token")
                self.token_expiry = datetime.utcnow() + timedelta(hours=2)
                
                # Clear the authorization code after use
                self.authorization_code = None
                
            except httpx.HTTPStatusError as e:
                error_data = e.response.json() if e.response.content else {}
                raise AuthenticationError(
                    f"Token exchange failed: {error_data.get('error_description', str(e))}",
                    auth_type="oauth2"
                )
    
    async def _refresh_access_token(self) -> None:
        """Refresh the access token using refresh token."""
        url = f"https://{self.domain}.salesforce.com/services/oauth2/token"
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=data)
                response.raise_for_status()
                
                result = response.json()
                self.access_token = result["access_token"]
                self.instance_url = result["instance_url"]
                self.token_expiry = datetime.utcnow() + timedelta(hours=2)
                
            except httpx.HTTPStatusError as e:
                error_data = e.response.json() if e.response.content else {}
                raise AuthenticationError(
                    f"Token refresh failed: {error_data.get('error_description', str(e))}",
                    auth_type="oauth2"
                )


class JWTAuth(AuthBase):
    """JWT Bearer Token Flow authentication."""
    
    def __init__(
        self,
        client_id: str,
        username: str,
        private_key_file: str,
        domain: str = "login",
        sandbox: bool = False
    ):
        super().__init__()
        self.client_id = client_id
        self.username = username
        self.private_key_file = private_key_file
        self.domain = domain
        self.sandbox = sandbox
        self._private_key = None
    
    def _load_private_key(self) -> Any:
        """Load the private key from file."""
        if not self._private_key:
            with open(self.private_key_file, 'rb') as key_file:
                self._private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                    backend=default_backend()
                )
        return self._private_key
    
    def _create_jwt_token(self) -> str:
        """Create a JWT token for authentication."""
        now = int(time.time())
        
        claims = {
            "iss": self.client_id,
            "sub": self.username,
            "aud": f"https://{self.domain}.salesforce.com",
            "exp": now + 300  # 5 minutes expiry
        }
        
        private_key = self._load_private_key()
        
        return jwt.encode(
            claims,
            private_key,
            algorithm="RS256"
        )
    
    async def authenticate(self) -> None:
        """Authenticate using JWT Bearer Token Flow."""
        url = f"https://{self.domain}.salesforce.com/services/oauth2/token"
        
        jwt_token = self._create_jwt_token()
        
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=data)
                response.raise_for_status()
                
                result = response.json()
                self.access_token = result["access_token"]
                self.instance_url = result["instance_url"]
                self.token_expiry = datetime.utcnow() + timedelta(hours=2)
                
            except httpx.HTTPStatusError as e:
                error_data = e.response.json() if e.response.content else {}
                raise AuthenticationError(
                    f"JWT authentication failed: {error_data.get('error_description', str(e))}",
                    auth_type="jwt"
                )