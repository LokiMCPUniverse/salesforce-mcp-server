"""Salesforce MCP Server implementation using FastMCP."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from .client import SalesforceClient, create_client_from_config
from .config import OrgConfig, SalesforceConfig
from .exceptions import SalesforceError

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context injected into every tool call."""

    config: SalesforceConfig
    orgs: dict[str, OrgConfig]
    default_org: str
    clients: dict[str, SalesforceClient] = field(default_factory=dict)
    audit_log_enabled: bool = True
    audit_log_file: str | None = None

    async def get_client(self, org_name: str | None = None) -> SalesforceClient:
        """Return (creating if necessary) a Salesforce client for the org."""
        name = org_name or self.default_org
        if name not in self.clients:
            if name not in self.orgs:
                org_config = self.config.get_org_config(name)
                if not org_config.username and not (org_config.client_id and org_config.client_secret):
                    raise ValueError(f"Unknown org: {name}")
                self.orgs[name] = org_config
            self.clients[name] = create_client_from_config(
                self.orgs[name],
                self.config.get_rate_limit_config(),
            )
        return self.clients[name]

    async def close(self) -> None:
        """Close all open clients."""
        for client in self.clients.values():
            try:
                if client._client is not None:
                    await client._client.aclose()
            except Exception:  # pragma: no cover - best effort
                logger.exception("Failed to close Salesforce client cleanly")
        self.clients.clear()

    def audit(self, event_type: str, data: dict[str, Any]) -> None:
        """Write an audit log entry, if audit logging is enabled."""
        if not self.audit_log_enabled:
            return
        entry = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        if self.audit_log_file:
            try:
                with open(self.audit_log_file, "a") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except Exception:
                logger.exception("Failed to write audit log to %s", self.audit_log_file)
        else:
            logger.info("Audit: %s", json.dumps(entry))


def _build_app_context(
    config: SalesforceConfig | None = None,
    orgs: dict[str, OrgConfig] | None = None,
    default_org: str | None = None,
) -> AppContext:
    """Construct an AppContext, deriving defaults from config where needed."""
    cfg = config or SalesforceConfig()
    resolved_orgs: dict[str, OrgConfig] = dict(orgs or {})
    # Seed default org from the base config if not already populated
    default_name = default_org or cfg.default_org
    if default_name not in resolved_orgs:
        resolved_orgs[default_name] = cfg.get_org_config()
    return AppContext(
        config=cfg,
        orgs=resolved_orgs,
        default_org=default_name,
        audit_log_enabled=cfg.enable_audit_log,
        audit_log_file=cfg.audit_log_file,
    )


@asynccontextmanager
async def _lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
    """Create and tear down the application context for the server lifetime."""
    ctx = _build_app_context()
    try:
        yield ctx
    finally:
        await ctx.close()


mcp = FastMCP("salesforce-mcp", lifespan=_lifespan)


def _app_ctx(ctx: Context) -> AppContext:
    """Get the typed AppContext from the MCP context."""
    return ctx.request_context.lifespan_context  # type: ignore[return-value]


async def _run_tool(
    ctx: Context,
    tool_name: str,
    org: str | None,
    fn,
) -> Any:
    """Shared wrapper that performs audit logging and error shaping."""
    app = _app_ctx(ctx)
    app.audit("tool_call", {"tool": tool_name, "org": org})
    try:
        client = await app.get_client(org)
        async with client:
            result = await fn(client)
        app.audit("tool_success", {"tool": tool_name, "org": org or app.default_org})
        return result
    except SalesforceError as exc:
        app.audit(
            "tool_error",
            {"tool": tool_name, "error": str(exc), "error_code": exc.error_code},
        )
        return {
            "error": exc.message,
            "error_code": exc.error_code,
            "details": exc.details,
        }


@mcp.tool()
async def salesforce_query(
    ctx: Context,
    query: str,
    include_deleted: bool = False,
    org: str | None = None,
) -> dict[str, Any]:
    """Execute a SOQL query. Set include_deleted=True to search IsDeleted records."""
    return await _run_tool(
        ctx,
        "salesforce_query",
        org,
        lambda c: c.query(query=query, include_deleted=include_deleted),
    )


@mcp.tool()
async def salesforce_get_record(
    ctx: Context,
    object_type: str,
    record_id: str,
    fields: list[str] | None = None,
    org: str | None = None,
) -> dict[str, Any]:
    """Retrieve a Salesforce record by ID, optionally limiting returned fields."""
    return await _run_tool(
        ctx,
        "salesforce_get_record",
        org,
        lambda c: c.get_record(object_type=object_type, record_id=record_id, fields=fields),
    )


@mcp.tool()
async def salesforce_create_record(
    ctx: Context,
    object_type: str,
    data: dict[str, Any],
    org: str | None = None,
) -> dict[str, Any]:
    """Create a new Salesforce record of the given object type."""

    async def _do(client: SalesforceClient) -> dict[str, Any]:
        result = await client.create_record(object_type=object_type, data=data)
        return {"success": True, "id": result.get("id"), "result": result}

    return await _run_tool(ctx, "salesforce_create_record", org, _do)


@mcp.tool()
async def salesforce_update_record(
    ctx: Context,
    object_type: str,
    record_id: str,
    data: dict[str, Any],
    org: str | None = None,
) -> dict[str, Any]:
    """Update fields on an existing Salesforce record."""

    async def _do(client: SalesforceClient) -> dict[str, Any]:
        await client.update_record(object_type=object_type, record_id=record_id, data=data)
        return {"success": True, "message": "Record updated successfully"}

    return await _run_tool(ctx, "salesforce_update_record", org, _do)


@mcp.tool()
async def salesforce_delete_record(
    ctx: Context,
    object_type: str,
    record_id: str,
    org: str | None = None,
) -> dict[str, Any]:
    """Delete a Salesforce record by ID."""

    async def _do(client: SalesforceClient) -> dict[str, Any]:
        await client.delete_record(object_type=object_type, record_id=record_id)
        return {"success": True, "message": "Record deleted successfully"}

    return await _run_tool(ctx, "salesforce_delete_record", org, _do)


@mcp.tool()
async def salesforce_describe_object(
    ctx: Context,
    object_type: str,
    org: str | None = None,
) -> dict[str, Any]:
    """Return field/metadata information for a Salesforce object."""
    return await _run_tool(
        ctx,
        "salesforce_describe_object",
        org,
        lambda c: c.describe_object(object_type=object_type),
    )


@mcp.tool()
async def salesforce_bulk_create(
    ctx: Context,
    object_type: str,
    records: list[dict[str, Any]],
    batch_size: int = 200,
    org: str | None = None,
) -> dict[str, Any]:
    """Insert multiple records using the Salesforce Bulk API 2.0."""

    async def _do(client: SalesforceClient) -> dict[str, Any]:
        result = await client.bulk_create(
            object_type=object_type,
            records=records,
            batch_size=batch_size,
        )
        return {
            "success": True,
            "job_id": result.get("id"),
            "state": result.get("state"),
            "records_processed": result.get("numberRecordsProcessed"),
            "records_failed": result.get("numberRecordsFailed"),
        }

    return await _run_tool(ctx, "salesforce_bulk_create", org, _do)


@mcp.tool()
async def salesforce_execute_apex(
    ctx: Context,
    apex_body: str,
    org: str | None = None,
) -> dict[str, Any]:
    """Execute anonymous Apex code."""

    async def _do(client: SalesforceClient) -> dict[str, Any]:
        result = await client.execute_apex(apex_body=apex_body)
        return {
            "success": True,
            "compiled": result.get("compiled"),
            "executed": result.get("success"),
            "logs": result.get("logs"),
        }

    return await _run_tool(ctx, "salesforce_execute_apex", org, _do)


@mcp.tool()
async def salesforce_list_objects(
    ctx: Context,
    org: str | None = None,
) -> dict[str, Any]:
    """List all Salesforce objects visible to the authenticated user."""

    async def _do(client: SalesforceClient) -> dict[str, Any]:
        result = await client.describe_global()
        return {
            "objects": [
                {
                    "name": obj["name"],
                    "label": obj["label"],
                    "custom": obj["custom"],
                    "queryable": obj["queryable"],
                }
                for obj in result.get("sobjects", [])
            ]
        }

    return await _run_tool(ctx, "salesforce_list_objects", org, _do)


@mcp.tool()
async def salesforce_run_report(
    ctx: Context,
    report_id: str,
    filters: dict[str, Any] | None = None,
    org: str | None = None,
) -> dict[str, Any]:
    """Run a Salesforce analytics report."""
    return await _run_tool(
        ctx,
        "salesforce_run_report",
        org,
        lambda c: c.run_report(report_id=report_id, filters=filters),
    )


@mcp.tool()
async def salesforce_query_more(
    ctx: Context,
    next_records_url: str,
    org: str | None = None,
) -> dict[str, Any]:
    """Retrieve the next page of a paginated SOQL query."""
    return await _run_tool(
        ctx,
        "salesforce_query_more",
        org,
        lambda c: c.query_more(next_records_url=next_records_url),
    )


@mcp.tool()
async def salesforce_search(
    ctx: Context,
    search_query: str,
    org: str | None = None,
) -> dict[str, Any]:
    """Execute a SOSL (Salesforce Object Search Language) search."""
    return await _run_tool(
        ctx,
        "salesforce_search",
        org,
        lambda c: c.search(search_query=search_query),
    )


@mcp.tool()
async def salesforce_limits(
    ctx: Context,
    org: str | None = None,
) -> dict[str, Any]:
    """Return the Salesforce organization's API limits and usage."""
    return await _run_tool(
        ctx,
        "salesforce_limits",
        org,
        lambda c: c.get_limits(),
    )


def main() -> None:
    """Entry point for the stdio server."""
    logging.basicConfig(level=os.environ.get("SALESFORCE_MCP_LOG_LEVEL", "INFO"))
    try:
        SalesforceConfig().validate_config()
    except Exception as exc:  # pragma: no cover - startup guard
        logger.exception("Invalid Salesforce MCP configuration")
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
