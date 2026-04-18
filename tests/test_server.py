"""Unit tests for the FastMCP Salesforce server surface."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest

from salesforce_mcp import server as server_module
from salesforce_mcp.client import SalesforceClient
from salesforce_mcp.config import OrgConfig, SalesforceConfig
from salesforce_mcp.exceptions import ValidationError
from salesforce_mcp.server import AppContext, _build_app_context, mcp


def _make_config() -> Mock:
    cfg = Mock(spec=SalesforceConfig)
    cfg.enable_audit_log = False
    cfg.audit_log_file = None
    cfg.default_org = "default"
    org = Mock(spec=OrgConfig)
    org.username = "test@example.com"
    cfg.get_org_config.return_value = org
    cfg.get_rate_limit_config.return_value = None
    return cfg


def _make_ctx(app: AppContext) -> Mock:
    request_context = SimpleNamespace(lifespan_context=app)
    ctx = Mock()
    ctx.request_context = request_context
    return ctx


@pytest.fixture()
def app() -> AppContext:
    cfg = _make_config()
    return AppContext(
        config=cfg,
        orgs={"default": cfg.get_org_config.return_value},
        default_org="default",
        audit_log_enabled=False,
    )


@pytest.fixture()
def ctx(app: AppContext) -> Mock:
    return _make_ctx(app)


def _install_client(app: AppContext, client: AsyncMock) -> None:
    # Make the async context manager yield the same client
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    app.clients["default"] = client


def test_mcp_name_and_tool_registry() -> None:
    assert mcp.name == "salesforce-mcp"


def test_build_app_context_uses_defaults() -> None:
    cfg = _make_config()
    app = _build_app_context(config=cfg)
    assert app.default_org == "default"
    assert "default" in app.orgs


@pytest.mark.asyncio
async def test_registered_tools_cover_expected_surface() -> None:
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "salesforce_query",
        "salesforce_get_record",
        "salesforce_create_record",
        "salesforce_update_record",
        "salesforce_delete_record",
        "salesforce_describe_object",
        "salesforce_bulk_create",
        "salesforce_execute_apex",
        "salesforce_list_objects",
        "salesforce_run_report",
        "salesforce_query_more",
        "salesforce_search",
        "salesforce_limits",
    }
    assert expected <= names


@pytest.mark.asyncio
async def test_salesforce_query_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.query.return_value = {
        "totalSize": 1,
        "done": True,
        "records": [{"Id": "001xx", "Name": "Test Account"}],
    }
    _install_client(app, client)

    result = await server_module.salesforce_query(
        ctx, query="SELECT Id, Name FROM Account LIMIT 1"
    )
    assert result["totalSize"] == 1
    client.query.assert_awaited_once_with(
        query="SELECT Id, Name FROM Account LIMIT 1", include_deleted=False
    )


@pytest.mark.asyncio
async def test_salesforce_create_record_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.create_record.return_value = {"id": "003xx", "success": True, "errors": []}
    _install_client(app, client)

    result = await server_module.salesforce_create_record(
        ctx, object_type="Contact", data={"FirstName": "Jane", "LastName": "Doe"}
    )
    assert result["success"] is True
    assert result["id"] == "003xx"


@pytest.mark.asyncio
async def test_salesforce_update_record_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.update_record.return_value = None
    _install_client(app, client)

    result = await server_module.salesforce_update_record(
        ctx,
        object_type="Contact",
        record_id="003xx",
        data={"Title": "Senior Developer"},
    )
    assert result["success"] is True
    assert "updated successfully" in result["message"]


@pytest.mark.asyncio
async def test_salesforce_delete_record_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.delete_record.return_value = None
    _install_client(app, client)

    result = await server_module.salesforce_delete_record(
        ctx, object_type="Contact", record_id="003xx"
    )
    assert result["success"] is True
    assert "deleted successfully" in result["message"]


@pytest.mark.asyncio
async def test_salesforce_bulk_create_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.bulk_create.return_value = {
        "id": "job-1",
        "state": "JobComplete",
        "numberRecordsProcessed": 2,
        "numberRecordsFailed": 0,
    }
    _install_client(app, client)

    result = await server_module.salesforce_bulk_create(
        ctx,
        object_type="Contact",
        records=[{"FirstName": "A"}, {"FirstName": "B"}],
    )
    assert result["records_processed"] == 2
    assert result["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_salesforce_execute_apex_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.execute_apex.return_value = {
        "compiled": True,
        "success": True,
        "logs": "log-output",
    }
    _install_client(app, client)

    result = await server_module.salesforce_execute_apex(
        ctx, apex_body="System.debug('hi');"
    )
    assert result["compiled"] is True
    assert result["success"] is True


@pytest.mark.asyncio
async def test_salesforce_list_objects_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.describe_global.return_value = {
        "sobjects": [
            {"name": "Account", "label": "Account", "custom": False, "queryable": True},
            {"name": "Foo__c", "label": "Foo", "custom": True, "queryable": True},
        ]
    }
    _install_client(app, client)

    result = await server_module.salesforce_list_objects(ctx)
    assert len(result["objects"]) == 2
    assert result["objects"][1]["custom"] is True


@pytest.mark.asyncio
async def test_salesforce_describe_object_tool(app: AppContext, ctx: Mock) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.describe_object.return_value = {
        "name": "Account",
        "label": "Account",
        "fields": [{"name": "Id", "type": "id"}],
    }
    _install_client(app, client)

    result = await server_module.salesforce_describe_object(ctx, object_type="Account")
    assert result["name"] == "Account"


@pytest.mark.asyncio
async def test_error_handling_returns_structured_error(
    app: AppContext, ctx: Mock
) -> None:
    client = AsyncMock(spec=SalesforceClient)
    client.query.side_effect = ValidationError(
        "MALFORMED_QUERY: bad token",
        field_errors={"query": ["bad"]},
    )
    _install_client(app, client)

    result = await server_module.salesforce_query(ctx, query="SELECT INVALID FROM X")
    assert "error" in result
    assert "MALFORMED_QUERY" in result["error"]


@pytest.mark.asyncio
async def test_unknown_org_raises() -> None:
    cfg = _make_config()
    org = Mock(spec=OrgConfig)
    org.username = None
    org.client_id = None
    org.client_secret = None
    cfg.get_org_config.return_value = org

    app = AppContext(
        config=cfg,
        orgs={},
        default_org="default",
    )
    with pytest.raises(ValueError, match="Unknown org"):
        await app.get_client("missing")


@pytest.mark.asyncio
async def test_multi_org_client_caching() -> None:
    cfg = _make_config()
    app = AppContext(
        config=cfg,
        orgs={
            "production": Mock(spec=OrgConfig),
            "sandbox": Mock(spec=OrgConfig),
        },
        default_org="production",
    )
    prod = AsyncMock(spec=SalesforceClient)
    sbx = AsyncMock(spec=SalesforceClient)
    with patch(
        "salesforce_mcp.server.create_client_from_config", side_effect=[prod, sbx]
    ):
        first = await app.get_client("production")
        second = await app.get_client("sandbox")
        cached = await app.get_client("production")

    assert first is prod
    assert second is sbx
    assert cached is prod


def test_audit_logging_writes_file(tmp_path) -> None:
    log_path = tmp_path / "audit.log"
    app = AppContext(
        config=_make_config(),
        orgs={},
        default_org="default",
        audit_log_enabled=True,
        audit_log_file=str(log_path),
    )
    with patch("builtins.open", mock_open()) as mock_file:
        app.audit("event", {"key": "value"})
        mock_file.assert_called_once_with(str(log_path), "a")
        handle = mock_file()
        written = handle.write.call_args[0][0]

    entry = json.loads(written.strip())
    assert entry["event_type"] == "event"
    assert entry["data"] == {"key": "value"}
    assert "timestamp" in entry
