"""Example of managing multiple Salesforce organizations.

This example constructs one `SalesforceClient` per configured org and then
performs cross-org operations. When running inside the MCP server itself,
each tool call simply passes the target ``org`` argument instead.
"""

import asyncio
import os
from typing import Any

from pydantic import SecretStr

from salesforce_mcp import OrgConfig, SalesforceConfig
from salesforce_mcp.client import SalesforceClient, create_client_from_config


class MultiOrgSalesforceManager:
    """Manages multiple Salesforce organizations via `SalesforceClient`."""

    def __init__(self) -> None:
        self.config = SalesforceConfig()
        self.orgs: dict[str, OrgConfig] = self._initialize_org_configs()
        self._clients: dict[str, SalesforceClient] = {}

    def _initialize_org_configs(self) -> dict[str, OrgConfig]:
        """Read per-org environment variables into `OrgConfig` instances."""
        orgs: dict[str, OrgConfig] = {}

        if os.getenv("SALESFORCE_PROD_USERNAME"):
            orgs["production"] = OrgConfig(
                username=os.getenv("SALESFORCE_PROD_USERNAME"),
                password=SecretStr(os.getenv("SALESFORCE_PROD_PASSWORD", "")),
                security_token=SecretStr(os.getenv("SALESFORCE_PROD_SECURITY_TOKEN", "")),
                domain="login",
                api_version="59.0",
            )

        if os.getenv("SALESFORCE_SANDBOX_USERNAME"):
            orgs["sandbox"] = OrgConfig(
                username=os.getenv("SALESFORCE_SANDBOX_USERNAME"),
                password=SecretStr(os.getenv("SALESFORCE_SANDBOX_PASSWORD", "")),
                security_token=SecretStr(os.getenv("SALESFORCE_SANDBOX_SECURITY_TOKEN", "")),
                domain="test",
                sandbox=True,
                api_version="59.0",
            )

        if os.getenv("SALESFORCE_DEV_USERNAME"):
            orgs["development"] = OrgConfig(
                username=os.getenv("SALESFORCE_DEV_USERNAME"),
                password=SecretStr(os.getenv("SALESFORCE_DEV_PASSWORD", "")),
                security_token=SecretStr(os.getenv("SALESFORCE_DEV_SECURITY_TOKEN", "")),
                domain=os.getenv("SALESFORCE_DEV_DOMAIN", "test"),
                sandbox=True,
                api_version="60.0",
            )

        if not orgs:
            orgs["default"] = self.config.get_org_config()

        return orgs

    def _client_for(self, org_name: str) -> SalesforceClient:
        if org_name not in self._clients:
            if org_name not in self.orgs:
                raise KeyError(f"Unknown org: {org_name}")
            self._clients[org_name] = create_client_from_config(
                self.orgs[org_name], self.config.get_rate_limit_config()
            )
        return self._clients[org_name]

    async def close(self) -> None:
        for client in self._clients.values():
            if client._client is not None:
                await client._client.aclose()

    async def sync_data_between_orgs(
        self,
        source_org: str,
        target_org: str,
        object_type: str,
        query: str,
    ) -> dict[str, Any]:
        """Copy records from ``source_org`` to ``target_org`` using Bulk API 2.0."""
        print(f"Syncing {object_type} from {source_org} to {target_org}")

        source = self._client_for(source_org)
        async with source:
            source_result = await source.query(query)

        records = source_result.get("records", [])
        print(f"Found {len(records)} records to sync")
        if not records:
            return {"synced": 0, "failed": 0, "message": "No records to sync"}

        system_fields = {
            "Id",
            "CreatedDate",
            "CreatedById",
            "LastModifiedDate",
            "LastModifiedById",
            "SystemModstamp",
            "IsDeleted",
        }
        cleaned = [
            {k: v for k, v in record.items() if k not in system_fields and not k.endswith("__r")}
            for record in records
        ]

        target = self._client_for(target_org)
        async with target:
            bulk = await target.bulk_create(object_type, cleaned, batch_size=200)

        processed = bulk.get("numberRecordsProcessed", 0)
        failed = bulk.get("numberRecordsFailed", 0)
        return {
            "synced": processed - failed,
            "failed": failed,
            "job_id": bulk.get("id"),
            "message": f"Sync completed for {object_type}",
        }

    async def compare_org_schemas(self, org1: str, org2: str) -> dict[str, Any]:
        print(f"Comparing schemas between {org1} and {org2}")

        c1 = self._client_for(org1)
        c2 = self._client_for(org2)
        async with c1, c2:
            g1 = await c1.describe_global()
            g2 = await c2.describe_global()

            o1 = {obj["name"]: obj for obj in g1.get("sobjects", [])}
            o2 = {obj["name"]: obj for obj in g2.get("sobjects", [])}

            only_in_org1 = set(o1) - set(o2)
            only_in_org2 = set(o2) - set(o1)
            common = set(o1) & set(o2)

            differences = []
            for name in list(common)[:5]:
                d1 = await c1.describe_object(name)
                d2 = await c2.describe_object(name)
                f1 = {f["name"]: f for f in d1.get("fields", [])}
                f2 = {f["name"]: f for f in d2.get("fields", [])}
                diff = {
                    "object": name,
                    "fields_only_in_org1": list(set(f1) - set(f2)),
                    "fields_only_in_org2": list(set(f2) - set(f1)),
                }
                if diff["fields_only_in_org1"] or diff["fields_only_in_org2"]:
                    differences.append(diff)

        return {
            "objects_only_in_org1": list(only_in_org1),
            "objects_only_in_org2": list(only_in_org2),
            "common_objects_count": len(common),
            "field_differences": differences,
        }

    async def run_report_across_orgs(self, query: str) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for org_name in self.orgs:
            try:
                print(f"Running query in {org_name}...")
                client = self._client_for(org_name)
                async with client:
                    result = await client.query(query)
                results[org_name] = {
                    "success": True,
                    "total_size": result.get("totalSize", 0),
                    "records": result.get("records", []),
                }
            except Exception as exc:
                results[org_name] = {"success": False, "error": str(exc)}
        return results


async def demonstrate_multi_org_operations() -> None:
    manager = MultiOrgSalesforceManager()
    try:
        print("Multi-Org Salesforce Management Demo")
        print("=" * 60)
        print()
        print("Available Organizations:")
        for name in manager.orgs:
            print(f"- {name}")
        print()

        print("Example 1: Account Count Across All Orgs")
        print("-" * 40)
        results = await manager.run_report_across_orgs(
            "SELECT COUNT(Id) total FROM Account"
        )
        for org, result in results.items():
            if result["success"]:
                total = result["records"][0]["total"] if result["records"] else 0
                print(f"{org}: {total} accounts")
            else:
                print(f"{org}: Error - {result['error']}")
        print()

        if len(manager.orgs) >= 2:
            names = list(manager.orgs)
            print(f"Example 2: Schema Comparison between {names[0]} and {names[1]}")
            print("-" * 40)
            comparison = await manager.compare_org_schemas(names[0], names[1])
            print(f"Objects only in {names[0]}: {len(comparison['objects_only_in_org1'])}")
            print(f"Objects only in {names[1]}: {len(comparison['objects_only_in_org2'])}")
            print(f"Common objects: {comparison['common_objects_count']}")
    finally:
        await manager.close()


def create_multi_org_config_example() -> str:
    return """
# Multi-Org Configuration Example
# Add these to your .env file or set as environment variables

# Production Organization
SALESFORCE_PROD_USERNAME=admin@company.com
SALESFORCE_PROD_PASSWORD=productionPassword123
SALESFORCE_PROD_SECURITY_TOKEN=prodSecurityToken
SALESFORCE_PROD_DOMAIN=login

# Sandbox Organization
SALESFORCE_SANDBOX_USERNAME=admin@company.com.sandbox
SALESFORCE_SANDBOX_PASSWORD=sandboxPassword123
SALESFORCE_SANDBOX_SECURITY_TOKEN=sandboxSecurityToken
SALESFORCE_SANDBOX_DOMAIN=test

# Development Organization
SALESFORCE_DEV_USERNAME=developer@company.com.dev
SALESFORCE_DEV_PASSWORD=devPassword123
SALESFORCE_DEV_SECURITY_TOKEN=devSecurityToken
SALESFORCE_DEV_DOMAIN=test
SALESFORCE_DEV_API_VERSION=60.0
"""


if __name__ == "__main__":
    print("Multi-Org Configuration Example")
    print("=" * 60)
    print(create_multi_org_config_example())
    print()

    has_config = any(
        [
            os.getenv("SALESFORCE_USERNAME"),
            os.getenv("SALESFORCE_PROD_USERNAME"),
            os.getenv("SALESFORCE_SANDBOX_USERNAME"),
            os.getenv("SALESFORCE_DEV_USERNAME"),
        ]
    )
    if not has_config:
        print("Error: No Salesforce organizations configured.")
        raise SystemExit(1)

    asyncio.run(demonstrate_multi_org_operations())
