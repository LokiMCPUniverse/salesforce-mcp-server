"""Unit tests for authentication modules."""

import pytest
import json
import jwt
import httpx
from unittest.mock import Mock, AsyncMock, patch, mock_open
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from salesforce_mcp.auth import (
    UsernamePasswordAuth,
    OAuth2Auth,
    JWTAuth
)
from salesforce_mcp.exceptions import AuthenticationError


class TestUsernamePasswordAuth:
    """Tests for username/password authentication."""
    
    @pytest.fixture
    def auth(self):
        """Create auth instance."""
        return UsernamePasswordAuth(
            username="test@example.com",
            password="password123",
            security_token="token123",
            domain="test"
        )
    
    @pytest.mark.asyncio
    async def test_successful_authentication(self, auth):
        """Test successful authentication."""
        mock_response = {
            "access_token": "test_access_token",
            "instance_url": "https://test.salesforce.com",
            "id": "https://test.salesforce.com/id/00Dxx0000000000EAA/005xx000000000TAAQ",
            "token_type": "Bearer",
            "issued_at": "1234567890",
            "signature": "test_signature"
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = Mock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = Mock()
            
            mock_client.post.return_value = mock_response_obj
            
            await auth.authenticate()
            
            assert auth.access_token == "test_access_token"
            assert auth.instance_url == "https://test.salesforce.com"
            assert auth.token_expiry > datetime.utcnow()
            
            # Check request parameters
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://test.salesforce.com/services/oauth2/token"
            assert call_args[1]["data"]["grant_type"] == "password"
            assert call_args[1]["data"]["username"] == "test@example.com"
            assert call_args[1]["data"]["password"] == "password123token123"
    
    @pytest.mark.asyncio
    async def test_authentication_with_client_credentials(self):
        """Test authentication with client ID and secret."""
        auth = UsernamePasswordAuth(
            username="test@example.com",
            password="password123",
            security_token="token123",
            domain="login",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = Mock()
            mock_response_obj.json.return_value = {
                "access_token": "test_token",
                "instance_url": "https://test.salesforce.com"
            }
            mock_response_obj.raise_for_status = Mock()
            
            mock_client.post.return_value = mock_response_obj
            
            await auth.authenticate()
            
            call_args = mock_client.post.call_args[1]["data"]
            assert call_args["client_id"] == "test_client_id"
            assert call_args["client_secret"] == "test_client_secret"
    
    @pytest.mark.asyncio
    async def test_authentication_failure(self, auth):
        """Test authentication failure."""
        error_response = Mock()
        error_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "authentication failure"
        }
        error_response.content = b'{"error": "invalid_grant"}'
        
        http_error = httpx.HTTPStatusError(
            "400 Bad Request",
            request=Mock(),
            response=error_response
        )
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = http_error
            
            with pytest.raises(AuthenticationError) as exc_info:
                await auth.authenticate()
            
            assert "authentication failure" in str(exc_info.value)
            assert exc_info.value.auth_type == "username_password"
    
    @pytest.mark.asyncio
    async def test_is_token_valid(self, auth):
        """Test token validity check."""
        # No token yet
        assert not auth.is_token_valid()
        
        # Set token and expiry
        auth.access_token = "test_token"
        auth.token_expiry = datetime.utcnow() + timedelta(hours=1)
        assert auth.is_token_valid()
        
        # Expired token
        auth.token_expiry = datetime.utcnow() - timedelta(hours=1)
        assert not auth.is_token_valid()
    
    @pytest.mark.asyncio
    async def test_get_headers(self, auth):
        """Test getting authentication headers."""
        auth.access_token = "test_token"
        auth.token_expiry = datetime.utcnow() + timedelta(hours=1)
        
        headers = await auth.get_headers()
        
        assert headers["Authorization"] == "Bearer test_token"
        assert headers["Content-Type"] == "application/json"


class TestOAuth2Auth:
    """Tests for OAuth 2.0 authentication."""
    
    @pytest.fixture
    def auth(self):
        """Create OAuth2 auth instance."""
        return OAuth2Auth(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="http://localhost:8080/callback",
            domain="test"
        )
    
    def test_get_authorization_url(self, auth):
        """Test authorization URL generation."""
        url = auth.get_authorization_url()
        
        assert "https://test.salesforce.com/services/oauth2/authorize" in url
        assert "response_type=code" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=http://localhost:8080/callback" in url
        assert "scope=full refresh_token" in url
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token(self, auth):
        """Test exchanging authorization code for token."""
        auth.set_authorization_code("test_auth_code")
        
        mock_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "instance_url": "https://test.salesforce.com",
            "token_type": "Bearer"
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = Mock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = Mock()
            
            mock_client.post.return_value = mock_response_obj
            
            await auth.authenticate()
            
            assert auth.access_token == "test_access_token"
            assert auth.refresh_token == "test_refresh_token"
            assert auth.instance_url == "https://test.salesforce.com"
            assert auth.authorization_code is None  # Should be cleared
            
            # Check request
            call_args = mock_client.post.call_args[1]["data"]
            assert call_args["grant_type"] == "authorization_code"
            assert call_args["code"] == "test_auth_code"
    
    @pytest.mark.asyncio
    async def test_refresh_access_token(self, auth):
        """Test refreshing access token."""
        auth.refresh_token = "test_refresh_token"
        
        mock_response = {
            "access_token": "new_access_token",
            "instance_url": "https://test.salesforce.com"
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = Mock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = Mock()
            
            mock_client.post.return_value = mock_response_obj
            
            await auth.authenticate()
            
            assert auth.access_token == "new_access_token"
            
            # Check request
            call_args = mock_client.post.call_args[1]["data"]
            assert call_args["grant_type"] == "refresh_token"
            assert call_args["refresh_token"] == "test_refresh_token"
    
    @pytest.mark.asyncio
    async def test_no_credentials_error(self, auth):
        """Test error when no credentials available."""
        with pytest.raises(AuthenticationError) as exc_info:
            await auth.authenticate()
        
        assert "No refresh token or authorization code" in str(exc_info.value)


class TestJWTAuth:
    """Tests for JWT Bearer Token authentication."""
    
    @pytest.fixture
    def private_key(self):
        """Generate a test private key."""
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
    
    @pytest.fixture
    def private_key_pem(self, private_key):
        """Get PEM encoded private key."""
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    @pytest.fixture
    def auth(self, tmp_path, private_key_pem):
        """Create JWT auth instance."""
        key_file = tmp_path / "private_key.pem"
        key_file.write_bytes(private_key_pem)
        
        return JWTAuth(
            client_id="test_client_id",
            username="test@example.com",
            private_key_file=str(key_file),
            domain="test"
        )
    
    def test_create_jwt_token(self, auth, private_key):
        """Test JWT token creation."""
        with patch.object(auth, '_load_private_key', return_value=private_key):
            token = auth._create_jwt_token()
            
            # Decode token to verify claims
            public_key = private_key.public_key()
            decoded = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="https://test.salesforce.com"
            )
            
            assert decoded["iss"] == "test_client_id"
            assert decoded["sub"] == "test@example.com"
            assert decoded["aud"] == "https://test.salesforce.com"
            assert "exp" in decoded
    
    @pytest.mark.asyncio
    async def test_authenticate_success(self, auth):
        """Test successful JWT authentication."""
        mock_response = {
            "access_token": "test_access_token",
            "instance_url": "https://test.salesforce.com",
            "token_type": "Bearer"
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = Mock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = Mock()
            
            mock_client.post.return_value = mock_response_obj
            
            await auth.authenticate()
            
            assert auth.access_token == "test_access_token"
            assert auth.instance_url == "https://test.salesforce.com"
            
            # Check request
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://test.salesforce.com/services/oauth2/token"
            assert call_args[1]["data"]["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
            assert "assertion" in call_args[1]["data"]
    
    def test_load_private_key(self, auth):
        """Test loading private key from file."""
        key = auth._load_private_key()
        assert key is not None
        
        # Should cache the key
        key2 = auth._load_private_key()
        assert key2 is key
    
    @pytest.mark.asyncio
    async def test_authentication_failure(self, auth):
        """Test JWT authentication failure."""
        error_response = Mock()
        error_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "JWT validation failed"
        }
        error_response.content = b'{"error": "invalid_grant"}'
        
        http_error = httpx.HTTPStatusError(
            "400 Bad Request",
            request=Mock(),
            response=error_response
        )
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = http_error
            
            with pytest.raises(AuthenticationError) as exc_info:
                await auth.authenticate()
            
            assert "JWT validation failed" in str(exc_info.value)
            assert exc_info.value.auth_type == "jwt"