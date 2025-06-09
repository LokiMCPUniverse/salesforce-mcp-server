"""Salesforce MCP Server implementation."""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Sequence
from datetime import datetime

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from .client import SalesforceClient, create_client_from_config
from .config import SalesforceConfig, OrgConfig
from .exceptions import SalesforceError


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SalesforceMCPServer:
    """MCP Server for Salesforce API integration."""
    
    def __init__(
        self,
        config: Optional[SalesforceConfig] = None,
        orgs: Optional[Dict[str, OrgConfig]] = None,
        default_org: str = "default"
    ):
        self.server = Server("salesforce-mcp")
        self.config = config or SalesforceConfig()
        self.orgs = orgs or {"default": self.config.get_org_config()}
        self.default_org = default_org
        self.clients: Dict[str, SalesforceClient] = {}
        
        # Register handlers
        self._register_handlers()
        
        # Audit log setup
        self.audit_log_enabled = self.config.enable_audit_log
        self.audit_log_file = self.config.audit_log_file
    
    def _register_handlers(self):
        """Register all tool handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """Return list of available tools."""
            return [
                types.Tool(
                    name="salesforce_query",
                    description="Execute a SOQL query",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "SOQL query to execute"},
                            "include_deleted": {"type": "boolean", "description": "Include deleted records", "default": False},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="salesforce_get_record",
                    description="Retrieve a specific record by ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_type": {"type": "string", "description": "Salesforce object type"},
                            "record_id": {"type": "string", "description": "Record ID"},
                            "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to retrieve"},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["object_type", "record_id"]
                    }
                ),
                types.Tool(
                    name="salesforce_create_record",
                    description="Create a new record",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_type": {"type": "string", "description": "Salesforce object type"},
                            "data": {"type": "object", "description": "Record data"},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["object_type", "data"]
                    }
                ),
                types.Tool(
                    name="salesforce_update_record",
                    description="Update an existing record",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_type": {"type": "string", "description": "Salesforce object type"},
                            "record_id": {"type": "string", "description": "Record ID"},
                            "data": {"type": "object", "description": "Fields to update"},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["object_type", "record_id", "data"]
                    }
                ),
                types.Tool(
                    name="salesforce_delete_record",
                    description="Delete a record",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_type": {"type": "string", "description": "Salesforce object type"},
                            "record_id": {"type": "string", "description": "Record ID"},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["object_type", "record_id"]
                    }
                ),
                types.Tool(
                    name="salesforce_describe_object",
                    description="Get metadata about a Salesforce object",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_type": {"type": "string", "description": "Salesforce object type"},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["object_type"]
                    }
                ),
                types.Tool(
                    name="salesforce_bulk_create",
                    description="Create multiple records using Bulk API",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_type": {"type": "string", "description": "Salesforce object type"},
                            "records": {"type": "array", "items": {"type": "object"}, "description": "Records to create"},
                            "batch_size": {"type": "integer", "description": "Batch size", "default": 200},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["object_type", "records"]
                    }
                ),
                types.Tool(
                    name="salesforce_execute_apex",
                    description="Execute anonymous Apex code",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "apex_body": {"type": "string", "description": "Apex code to execute"},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["apex_body"]
                    }
                ),
                types.Tool(
                    name="salesforce_list_objects",
                    description="List all available Salesforce objects",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "org": {"type": "string", "description": "Target org name"}
                        }
                    }
                ),
                types.Tool(
                    name="salesforce_run_report",
                    description="Run a Salesforce report",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "report_id": {"type": "string", "description": "Report ID"},
                            "filters": {"type": "object", "description": "Report filters"},
                            "org": {"type": "string", "description": "Target org name"}
                        },
                        "required": ["report_id"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(
            name: str,
            arguments: Optional[Dict[str, Any]] = None
        ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """Handle tool execution."""
            try:
                # Log the tool call
                await self._audit_log("tool_call", {
                    "tool": name,
                    "arguments": arguments,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Get the appropriate client
                org_name = arguments.get("org", self.default_org) if arguments else self.default_org
                client = await self._get_client(org_name)
                
                # Execute the tool
                result = await self._execute_tool(name, arguments or {}, client)
                
                # Log success
                await self._audit_log("tool_success", {
                    "tool": name,
                    "org": org_name,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                return [types.TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]
                
            except SalesforceError as e:
                # Log error
                await self._audit_log("tool_error", {
                    "tool": name,
                    "error": str(e),
                    "error_code": e.error_code,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                error_response = {
                    "error": e.message,
                    "error_code": e.error_code,
                    "details": e.details
                }
                
                return [types.TextContent(
                    type="text",
                    text=json.dumps(error_response, indent=2)
                )]
            
            except Exception as e:
                logger.exception(f"Unexpected error in tool {name}")
                error_response = {
                    "error": str(e),
                    "error_type": type(e).__name__
                }
                
                return [types.TextContent(
                    type="text",
                    text=json.dumps(error_response, indent=2)
                )]
    
    async def _get_client(self, org_name: str) -> SalesforceClient:
        """Get or create a client for the specified org."""
        if org_name not in self.clients:
            if org_name not in self.orgs:
                # Try to load from environment
                org_config = self.config.get_org_config(org_name)
                if not org_config.username:
                    raise ValueError(f"Unknown org: {org_name}")
                self.orgs[org_name] = org_config
            
            self.clients[org_name] = create_client_from_config(
                self.orgs[org_name],
                self.config.get_rate_limit_config()
            )
        
        return self.clients[org_name]
    
    async def _execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        client: SalesforceClient
    ) -> Dict[str, Any]:
        """Execute a specific tool."""
        # Remove org from arguments as it's not needed by the client methods
        arguments = {k: v for k, v in arguments.items() if k != "org"}
        
        async with client:
            if name == "salesforce_query":
                return await client.query(**arguments)
            
            elif name == "salesforce_get_record":
                return await client.get_record(**arguments)
            
            elif name == "salesforce_create_record":
                result = await client.create_record(**arguments)
                return {"success": True, "id": result.get("id"), "result": result}
            
            elif name == "salesforce_update_record":
                await client.update_record(**arguments)
                return {"success": True, "message": "Record updated successfully"}
            
            elif name == "salesforce_delete_record":
                await client.delete_record(**arguments)
                return {"success": True, "message": "Record deleted successfully"}
            
            elif name == "salesforce_describe_object":
                return await client.describe_object(**arguments)
            
            elif name == "salesforce_bulk_create":
                result = await client.bulk_create(**arguments)
                return {
                    "success": True,
                    "job_id": result.get("id"),
                    "state": result.get("state"),
                    "records_processed": result.get("numberRecordsProcessed"),
                    "records_failed": result.get("numberRecordsFailed")
                }
            
            elif name == "salesforce_execute_apex":
                result = await client.execute_apex(**arguments)
                return {
                    "success": True,
                    "compiled": result.get("compiled"),
                    "executed": result.get("success"),
                    "logs": result.get("logs")
                }
            
            elif name == "salesforce_list_objects":
                result = await client.describe_global()
                return {
                    "objects": [
                        {
                            "name": obj["name"],
                            "label": obj["label"],
                            "custom": obj["custom"],
                            "queryable": obj["queryable"]
                        }
                        for obj in result.get("sobjects", [])
                    ]
                }
            
            elif name == "salesforce_run_report":
                return await client.run_report(**arguments)
            
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    async def _audit_log(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log audit events."""
        if not self.audit_log_enabled:
            return
        
        log_entry = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        
        if self.audit_log_file:
            try:
                with open(self.audit_log_file, "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")
        else:
            logger.info(f"Audit: {json.dumps(log_entry)}")
    
    async def run(self):
        """Run the MCP server."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="salesforce-mcp",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )


def main():
    """Main entry point."""
    import sys
    
    try:
        # Load configuration
        config = SalesforceConfig()
        config.validate_config()
        
        # Create and run server
        server = SalesforceMCPServer(config)
        asyncio.run(server.run())
        
    except Exception as e:
        logger.exception("Failed to start Salesforce MCP Server")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()