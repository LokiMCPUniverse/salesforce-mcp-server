"""Unit tests for Salesforce MCP server."""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

import mcp.types as types
from salesforce_mcp.server import SalesforceMCPServer
from salesforce_mcp.config import SalesforceConfig, OrgConfig
from salesforce_mcp.client import SalesforceClient
from salesforce_mcp.exceptions import ValidationError, ObjectNotFoundError


@pytest.fixture
def config():
    """Create test configuration."""
    config = Mock(spec=SalesforceConfig)
    config.enable_audit_log = False
    config.audit_log_file = None
    config.get_org_config.return_value = Mock(spec=OrgConfig)
    config.get_rate_limit_config.return_value = None
    config.validate_config.return_value = True
    return config


@pytest.fixture
def server(config):
    """Create test server instance."""
    return SalesforceMCPServer(config=config)


@pytest.mark.asyncio
async def test_list_tools(server):
    """Test listing available tools."""
    tools = await server.server.list_tools()
    
    tool_names = [tool.name for tool in tools]
    
    expected_tools = [
        "salesforce_query",
        "salesforce_get_record",
        "salesforce_create_record",
        "salesforce_update_record",
        "salesforce_delete_record",
        "salesforce_describe_object",
        "salesforce_bulk_create",
        "salesforce_execute_apex",
        "salesforce_list_objects",
        "salesforce_run_report"
    ]
    
    for expected in expected_tools:
        assert expected in tool_names
    
    # Check a specific tool schema
    query_tool = next(t for t in tools if t.name == "salesforce_query")
    assert "query" in query_tool.inputSchema["required"]
    assert "include_deleted" in query_tool.inputSchema["properties"]


@pytest.mark.asyncio
async def test_execute_query_tool(server):
    """Test executing a query tool."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.query.return_value = {
        "totalSize": 1,
        "done": True,
        "records": [{"Id": "001xx000003DHPh", "Name": "Test Account"}]
    }
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_query",
                {"query": "SELECT Id, Name FROM Account LIMIT 1"}
            )
    
    assert len(result) == 1
    assert result[0].type == "text"
    
    response_data = json.loads(result[0].text)
    assert response_data["totalSize"] == 1
    assert response_data["records"][0]["Name"] == "Test Account"


@pytest.mark.asyncio
async def test_execute_create_record_tool(server):
    """Test creating a record."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.create_record.return_value = {
        "id": "003xx000004TMM2",
        "success": True,
        "errors": []
    }
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_create_record",
                {
                    "object_type": "Contact",
                    "data": {
                        "FirstName": "John",
                        "LastName": "Doe",
                        "Email": "john.doe@example.com"
                    }
                }
            )
    
    response_data = json.loads(result[0].text)
    assert response_data["success"] is True
    assert response_data["id"] == "003xx000004TMM2"


@pytest.mark.asyncio
async def test_execute_update_record_tool(server):
    """Test updating a record."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.update_record.return_value = None
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_update_record",
                {
                    "object_type": "Contact",
                    "record_id": "003xx000004TMM2",
                    "data": {"Title": "Senior Developer"}
                }
            )
    
    response_data = json.loads(result[0].text)
    assert response_data["success"] is True
    assert "updated successfully" in response_data["message"]


@pytest.mark.asyncio
async def test_execute_delete_record_tool(server):
    """Test deleting a record."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.delete_record.return_value = None
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_delete_record",
                {
                    "object_type": "Contact",
                    "record_id": "003xx000004TMM2"
                }
            )
    
    response_data = json.loads(result[0].text)
    assert response_data["success"] is True
    assert "deleted successfully" in response_data["message"]


@pytest.mark.asyncio
async def test_execute_bulk_create_tool(server):
    """Test bulk creating records."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.bulk_create.return_value = {
        "id": "7501t00000Ao0YmAAJ",
        "state": "JobComplete",
        "numberRecordsProcessed": 2,
        "numberRecordsFailed": 0
    }
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_bulk_create",
                {
                    "object_type": "Contact",
                    "records": [
                        {"FirstName": "Jane", "LastName": "Doe"},
                        {"FirstName": "Bob", "LastName": "Smith"}
                    ]
                }
            )
    
    response_data = json.loads(result[0].text)
    assert response_data["success"] is True
    assert response_data["records_processed"] == 2
    assert response_data["records_failed"] == 0


@pytest.mark.asyncio
async def test_execute_apex_tool(server):
    """Test executing Apex code."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.execute_apex.return_value = {
        "compiled": True,
        "success": True,
        "logs": "Execute Anonymous: System.debug('Hello');"
    }
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_execute_apex",
                {"apex_body": "System.debug('Hello');"}
            )
    
    response_data = json.loads(result[0].text)
    assert response_data["success"] is True
    assert response_data["compiled"] is True


@pytest.mark.asyncio
async def test_error_handling(server):
    """Test error handling in tool execution."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.query.side_effect = ValidationError(
        "MALFORMED_QUERY: unexpected token: INVALID",
        field_errors={"query": ["Invalid SOQL syntax"]}
    )
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock) as mock_audit:
            result = await server.server.call_tool(
                "salesforce_query",
                {"query": "SELECT INVALID FROM Account"}
            )
    
    response_data = json.loads(result[0].text)
    assert "error" in response_data
    assert "MALFORMED_QUERY" in response_data["error"]
    
    # Check audit log was called for error
    audit_calls = [call for call in mock_audit.call_args_list if call[0][0] == "tool_error"]
    assert len(audit_calls) > 0


@pytest.mark.asyncio
async def test_multi_org_support(server):
    """Test multi-org support."""
    # Set up multiple orgs
    server.orgs = {
        "production": Mock(spec=OrgConfig),
        "sandbox": Mock(spec=OrgConfig)
    }
    
    mock_client_prod = AsyncMock(spec=SalesforceClient)
    mock_client_sandbox = AsyncMock(spec=SalesforceClient)
    
    mock_client_prod.query.return_value = {"org": "production"}
    mock_client_sandbox.query.return_value = {"org": "sandbox"}
    
    with patch('salesforce_mcp.server.create_client_from_config') as mock_create:
        mock_create.side_effect = [mock_client_prod, mock_client_sandbox]
        
        # Query from production
        client1 = await server._get_client("production")
        assert client1 is mock_client_prod
        
        # Query from sandbox
        client2 = await server._get_client("sandbox")
        assert client2 is mock_client_sandbox
        
        # Clients should be cached
        client3 = await server._get_client("production")
        assert client3 is mock_client_prod


@pytest.mark.asyncio
async def test_audit_logging_enabled(config):
    """Test audit logging when enabled."""
    config.enable_audit_log = True
    config.audit_log_file = "/tmp/audit.log"
    
    server = SalesforceMCPServer(config=config)
    
    with patch("builtins.open", mock_open()) as mock_file:
        await server._audit_log("test_event", {"key": "value"})
        
        mock_file.assert_called_once_with("/tmp/audit.log", "a")
        handle = mock_file()
        written_data = handle.write.call_args[0][0]
        
        log_entry = json.loads(written_data.strip())
        assert log_entry["event_type"] == "test_event"
        assert log_entry["data"]["key"] == "value"
        assert "timestamp" in log_entry


@pytest.mark.asyncio
async def test_unknown_tool_error(server):
    """Test handling of unknown tool."""
    with patch.object(server, '_audit_log', new_callable=AsyncMock):
        result = await server.server.call_tool(
            "salesforce_unknown_tool",
            {}
        )
    
    response_data = json.loads(result[0].text)
    assert "error" in response_data
    assert "Unknown tool" in response_data["error"]


@pytest.mark.asyncio
async def test_list_objects_tool(server):
    """Test listing Salesforce objects."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.describe_global.return_value = {
        "sobjects": [
            {
                "name": "Account",
                "label": "Account",
                "custom": False,
                "queryable": True
            },
            {
                "name": "CustomObject__c",
                "label": "Custom Object",
                "custom": True,
                "queryable": True
            }
        ]
    }
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_list_objects",
                {}
            )
    
    response_data = json.loads(result[0].text)
    assert len(response_data["objects"]) == 2
    assert response_data["objects"][0]["name"] == "Account"
    assert response_data["objects"][1]["custom"] is True


@pytest.mark.asyncio
async def test_describe_object_tool(server):
    """Test describing a Salesforce object."""
    mock_client = AsyncMock(spec=SalesforceClient)
    mock_client.describe_object.return_value = {
        "name": "Account",
        "label": "Account",
        "fields": [
            {"name": "Id", "type": "id", "label": "Account ID"},
            {"name": "Name", "type": "string", "label": "Account Name"}
        ]
    }
    
    with patch.object(server, '_get_client', return_value=mock_client):
        with patch.object(server, '_audit_log', new_callable=AsyncMock):
            result = await server.server.call_tool(
                "salesforce_describe_object",
                {"object_type": "Account"}
            )
    
    response_data = json.loads(result[0].text)
    assert response_data["name"] == "Account"
    assert len(response_data["fields"]) == 2