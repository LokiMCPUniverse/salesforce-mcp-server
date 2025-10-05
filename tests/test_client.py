"""Unit tests for Salesforce client."""

import asyncio
import pytest
import httpx
from unittest.mock import Mock, AsyncMock, patch

from salesforce_mcp.client import SalesforceClient, RateLimiter
from salesforce_mcp.auth import UsernamePasswordAuth
from salesforce_mcp.config import RateLimitConfig
from salesforce_mcp.exceptions import (
    ValidationError,
    ObjectNotFoundError,
    RateLimitError,
    ApexExecutionError
)


@pytest.fixture
def mock_auth():
    """Create a mock authentication instance."""
    auth = Mock(spec=UsernamePasswordAuth)
    auth.instance_url = "https://test.salesforce.com"
    auth.access_token = "test_token"
    auth.is_token_valid = Mock(return_value=True)
    auth.get_headers = AsyncMock(return_value={
        "Authorization": "Bearer test_token",
        "Content-Type": "application/json"
    })
    auth.authenticate = AsyncMock()
    return auth


@pytest.fixture
def client(mock_auth):
    """Create a test client."""
    return SalesforceClient(auth=mock_auth)


@pytest.mark.asyncio
async def test_query_success(client, mock_auth):
    """Test successful SOQL query."""
    expected_response = {
        "totalSize": 2,
        "done": True,
        "records": [
            {"Id": "001xx000003DHPh", "Name": "Test Account 1"},
            {"Id": "001xx000003DHPi", "Name": "Test Account 2"}
        ]
    }
    
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = expected_response
        
        result = await client.query("SELECT Id, Name FROM Account")
        
        assert result == expected_response
        mock_request.assert_called_once_with(
            "GET",
            "/services/data/v59.0/query",
            params={"q": "SELECT Id, Name FROM Account"}
        )


@pytest.mark.asyncio
async def test_query_with_deleted_records(client):
    """Test SOQL query including deleted records."""
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        await client.query("SELECT Id FROM Account", include_deleted=True)
        
        mock_request.assert_called_once_with(
            "GET",
            "/services/data/v59.0/queryAll",
            params={"q": "SELECT Id FROM Account"}
        )


@pytest.mark.asyncio
async def test_get_record_success(client):
    """Test successful record retrieval."""
    expected_response = {
        "Id": "001xx000003DHPh",
        "Name": "Test Account",
        "Industry": "Technology"
    }
    
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = expected_response
        
        result = await client.get_record("Account", "001xx000003DHPh", ["Name", "Industry"])
        
        assert result == expected_response
        mock_request.assert_called_once_with(
            "GET",
            "/services/data/v59.0/sobjects/Account/001xx000003DHPh",
            params={"fields": "Name,Industry"}
        )


@pytest.mark.asyncio
async def test_create_record_success(client):
    """Test successful record creation."""
    expected_response = {
        "id": "003xx000004TMM2",
        "success": True,
        "errors": []
    }
    
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = expected_response
        
        data = {
            "FirstName": "John",
            "LastName": "Doe",
            "Email": "john.doe@example.com"
        }
        
        result = await client.create_record("Contact", data)
        
        assert result == expected_response
        mock_request.assert_called_once_with(
            "POST",
            "/services/data/v59.0/sobjects/Contact",
            data=data
        )


@pytest.mark.asyncio
async def test_update_record_success(client):
    """Test successful record update."""
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {}
        
        data = {"Title": "Senior Developer"}
        
        await client.update_record("Contact", "003xx000004TMM2", data)
        
        mock_request.assert_called_once_with(
            "PATCH",
            "/services/data/v59.0/sobjects/Contact/003xx000004TMM2",
            data=data
        )


@pytest.mark.asyncio
async def test_delete_record_success(client):
    """Test successful record deletion."""
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {}
        
        await client.delete_record("Contact", "003xx000004TMM2")
        
        mock_request.assert_called_once_with(
            "DELETE",
            "/services/data/v59.0/sobjects/Contact/003xx000004TMM2"
        )


@pytest.mark.asyncio
async def test_validation_error(client):
    """Test handling of validation errors."""
    error_response = Mock()
    error_response.status_code = 400
    error_response.json.return_value = [{
        "message": "Required fields are missing: [LastName]",
        "errorCode": "REQUIRED_FIELD_MISSING",
        "fields": ["LastName"]
    }]
    
    error = httpx.HTTPStatusError(
        "400 Bad Request",
        request=Mock(),
        response=error_response
    )
    
    with patch.object(client, '_client') as mock_client:
        mock_client.request = AsyncMock(side_effect=error)
        
        with pytest.raises(ValidationError) as exc_info:
            await client.create_record("Contact", {"FirstName": "John"})
        
        assert "Required fields are missing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_not_found_error(client):
    """Test handling of not found errors."""
    error_response = Mock()
    error_response.status_code = 404
    error_response.json.return_value = [{
        "message": "The requested resource does not exist",
        "errorCode": "NOT_FOUND"
    }]
    
    error = httpx.HTTPStatusError(
        "404 Not Found",
        request=Mock(),
        response=error_response
    )
    
    with patch.object(client, '_client') as mock_client:
        mock_client.request = AsyncMock(side_effect=error)
        
        with pytest.raises(ObjectNotFoundError):
            await client.get_record("Account", "invalid_id")


@pytest.mark.asyncio
async def test_rate_limit_error(client):
    """Test handling of rate limit errors."""
    error_response = Mock()
    error_response.status_code = 429
    error_response.headers = {"Retry-After": "120"}
    error_response.json.return_value = [{
        "message": "Request limit exceeded",
        "errorCode": "REQUEST_LIMIT_EXCEEDED"
    }]
    
    error = httpx.HTTPStatusError(
        "429 Too Many Requests",
        request=Mock(),
        response=error_response
    )
    
    with patch.object(client, '_client') as mock_client:
        mock_client.request = AsyncMock(side_effect=error)
        
        with pytest.raises(RateLimitError) as exc_info:
            await client.query("SELECT Id FROM Account")
        
        assert exc_info.value.retry_after == 120


@pytest.mark.asyncio
async def test_token_refresh_on_401(client, mock_auth):
    """Test automatic token refresh on 401 error."""
    # First request returns 401, second succeeds
    error_response = Mock()
    error_response.status_code = 401
    error_response.json.return_value = [{"message": "Session expired"}]
    
    error = httpx.HTTPStatusError(
        "401 Unauthorized",
        request=Mock(),
        response=error_response
    )
    
    success_response = Mock()
    success_response.status_code = 200
    success_response.json.return_value = {"success": True}
    success_response.raise_for_status = Mock()
    
    with patch.object(client, '_client') as mock_client:
        mock_client.request = AsyncMock(side_effect=[error, success_response])
        
        result = await client.query("SELECT Id FROM Account")
        
        assert result == {"success": True}
        assert mock_auth.authenticate.call_count == 1


@pytest.mark.asyncio
async def test_execute_apex_success(client):
    """Test successful Apex execution."""
    expected_response = {
        "compiled": True,
        "compileProblem": None,
        "success": True,
        "line": -1,
        "column": -1,
        "exceptionMessage": None,
        "exceptionStackTrace": None,
        "logs": "Execute Anonymous: System.debug('Hello');"
    }
    
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = expected_response
        
        result = await client.execute_apex("System.debug('Hello');")
        
        assert result == expected_response


@pytest.mark.asyncio
async def test_execute_apex_compile_error(client):
    """Test Apex compilation error."""
    error_response = {
        "compiled": False,
        "compileProblem": "Variable does not exist: invalidVar",
        "success": False,
        "line": 1,
        "column": 14
    }
    
    with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = error_response
        
        with pytest.raises(ApexExecutionError) as exc_info:
            await client.execute_apex("System.debug(invalidVar);")
        
        assert exc_info.value.compile_error == "Variable does not exist: invalidVar"
        assert exc_info.value.line_number == 1


@pytest.mark.asyncio
async def test_rate_limiter():
    """Test rate limiter functionality."""
    config = RateLimitConfig(
        requests_per_second=2,
        burst_size=3,
        wait_on_limit=True
    )
    
    limiter = RateLimiter(config)
    
    # Should allow burst
    start_time = asyncio.get_event_loop().time()
    for _ in range(3):
        await limiter.acquire()
    
    # Fourth request should wait
    await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - start_time
    
    # Should have waited approximately 0.5 seconds
    assert elapsed >= 0.4  # Allow some tolerance


@pytest.mark.asyncio
async def test_rate_limiter_no_wait():
    """Test rate limiter without waiting."""
    config = RateLimitConfig(
        requests_per_second=1,
        burst_size=1,
        wait_on_limit=False
    )
    
    limiter = RateLimiter(config)
    
    # First request should succeed
    await limiter.acquire()
    
    # Second request should raise error
    with pytest.raises(RateLimitError):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_bulk_create_csv_conversion(client):
    """Test CSV conversion for bulk API."""
    records = [
        {"FirstName": "John", "LastName": "Doe", "Email": "john@example.com"},
        {"FirstName": "Jane", "LastName": "Smith", "Email": "jane@example.com"}
    ]
    
    csv_data = client._records_to_csv(records)
    
    expected_csv = "Email,FirstName,LastName\njohn@example.com,John,Doe\njane@example.com,Jane,Smith"
    assert csv_data == expected_csv


@pytest.mark.asyncio
async def test_context_manager(mock_auth):
    """Test client as async context manager."""
    client = SalesforceClient(auth=mock_auth)
    
    async with client as c:
        assert c._client is not None
        assert isinstance(c._client, httpx.AsyncClient)
    
    # Client should be closed after context
    if client._client:
        assert client._client.is_closed