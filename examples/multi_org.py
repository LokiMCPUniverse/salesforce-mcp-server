"""Example of managing multiple Salesforce organizations with MCP Server."""

import asyncio
import os
from typing import Dict, Any
from salesforce_mcp import SalesforceMCPServer, OrgConfig, SalesforceConfig
from pydantic import SecretStr


class MultiOrgSalesforceManager:
    """
    Manages multiple Salesforce organizations through the MCP Server.
    
    This is useful for companies that have:
    - Production and sandbox environments
    - Multiple business units with separate orgs
    - Client-specific Salesforce instances
    """
    
    def __init__(self):
        self.server = self._initialize_multi_org_server()
    
    def _initialize_multi_org_server(self) -> SalesforceMCPServer:
        """Initialize server with multiple org configurations."""
        
        # Define org configurations
        orgs = {}
        
        # Production org (from environment variables)
        if os.getenv("SALESFORCE_PROD_USERNAME"):
            orgs["production"] = OrgConfig(
                username=os.getenv("SALESFORCE_PROD_USERNAME"),
                password=SecretStr(os.getenv("SALESFORCE_PROD_PASSWORD", "")),
                security_token=SecretStr(os.getenv("SALESFORCE_PROD_SECURITY_TOKEN", "")),
                domain="login",
                api_version="59.0"
            )
        
        # Sandbox org
        if os.getenv("SALESFORCE_SANDBOX_USERNAME"):
            orgs["sandbox"] = OrgConfig(
                username=os.getenv("SALESFORCE_SANDBOX_USERNAME"),
                password=SecretStr(os.getenv("SALESFORCE_SANDBOX_PASSWORD", "")),
                security_token=SecretStr(os.getenv("SALESFORCE_SANDBOX_SECURITY_TOKEN", "")),
                domain="test",  # Sandbox uses test.salesforce.com
                sandbox=True,
                api_version="59.0"
            )
        
        # Developer org
        if os.getenv("SALESFORCE_DEV_USERNAME"):
            orgs["development"] = OrgConfig(
                username=os.getenv("SALESFORCE_DEV_USERNAME"),
                password=SecretStr(os.getenv("SALESFORCE_DEV_PASSWORD", "")),
                security_token=SecretStr(os.getenv("SALESFORCE_DEV_SECURITY_TOKEN", "")),
                domain=os.getenv("SALESFORCE_DEV_DOMAIN", "test"),
                sandbox=True,
                api_version="60.0"  # Dev org might use newer API version
            )
        
        # Client-specific org example
        if os.getenv("SALESFORCE_CLIENT_ACME_USERNAME"):
            orgs["client_acme"] = OrgConfig(
                username=os.getenv("SALESFORCE_CLIENT_ACME_USERNAME"),
                password=SecretStr(os.getenv("SALESFORCE_CLIENT_ACME_PASSWORD", "")),
                security_token=SecretStr(os.getenv("SALESFORCE_CLIENT_ACME_SECURITY_TOKEN", "")),
                domain=os.getenv("SALESFORCE_CLIENT_ACME_DOMAIN", "acme.my"),  # Custom domain
                api_version="59.0"
            )
        
        # Fallback to default config if no specific orgs are configured
        if not orgs:
            config = SalesforceConfig()
            orgs["default"] = config.get_org_config()
        
        return SalesforceMCPServer(orgs=orgs, default_org=list(orgs.keys())[0])
    
    async def sync_data_between_orgs(
        self,
        source_org: str,
        target_org: str,
        object_type: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Sync data from one org to another.
        
        Args:
            source_org: Name of the source organization
            target_org: Name of the target organization
            object_type: Salesforce object type to sync
            query: SOQL query to select records to sync
        
        Returns:
            Summary of the sync operation
        """
        print(f"Syncing {object_type} from {source_org} to {target_org}")
        
        # Get records from source org
        source_client = await self.server._get_client(source_org)
        source_result = await self.server._execute_tool(
            "salesforce_query",
            {"query": query},
            source_client
        )
        
        records = source_result.get("records", [])
        print(f"Found {len(records)} records to sync")
        
        if not records:
            return {"synced": 0, "failed": 0, "message": "No records to sync"}
        
        # Prepare records for target org (remove system fields)
        system_fields = ['Id', 'CreatedDate', 'CreatedById', 'LastModifiedDate', 
                        'LastModifiedById', 'SystemModstamp', 'IsDeleted']
        
        cleaned_records = []
        for record in records:
            cleaned_record = {
                k: v for k, v in record.items() 
                if k not in system_fields and not k.endswith('__r')
            }
            cleaned_records.append(cleaned_record)
        
        # Create records in target org using bulk API
        target_client = await self.server._get_client(target_org)
        bulk_result = await self.server._execute_tool(
            "salesforce_bulk_create",
            {
                "object_type": object_type,
                "records": cleaned_records,
                "batch_size": 200
            },
            target_client
        )
        
        return {
            "synced": bulk_result.get("records_processed", 0) - bulk_result.get("records_failed", 0),
            "failed": bulk_result.get("records_failed", 0),
            "job_id": bulk_result.get("job_id"),
            "message": f"Sync completed for {object_type}"
        }
    
    async def compare_org_schemas(self, org1: str, org2: str) -> Dict[str, Any]:
        """
        Compare object schemas between two organizations.
        
        Useful for:
        - Validating deployments
        - Ensuring org compatibility
        - Identifying customization differences
        """
        print(f"Comparing schemas between {org1} and {org2}")
        
        # Get object lists from both orgs
        client1 = await self.server._get_client(org1)
        client2 = await self.server._get_client(org2)
        
        objects1_result = await self.server._execute_tool(
            "salesforce_list_objects", {}, client1
        )
        objects2_result = await self.server._execute_tool(
            "salesforce_list_objects", {}, client2
        )
        
        objects1 = {obj['name']: obj for obj in objects1_result['objects']}
        objects2 = {obj['name']: obj for obj in objects2_result['objects']}
        
        # Find differences
        only_in_org1 = set(objects1.keys()) - set(objects2.keys())
        only_in_org2 = set(objects2.keys()) - set(objects1.keys())
        common_objects = set(objects1.keys()) & set(objects2.keys())
        
        # Compare common objects
        differences = []
        for obj_name in list(common_objects)[:5]:  # Limit to 5 for demo
            # Get detailed descriptions
            desc1 = await self.server._execute_tool(
                "salesforce_describe_object",
                {"object_type": obj_name},
                client1
            )
            desc2 = await self.server._execute_tool(
                "salesforce_describe_object",
                {"object_type": obj_name},
                client2
            )
            
            fields1 = {f['name']: f for f in desc1.get('fields', [])}
            fields2 = {f['name']: f for f in desc2.get('fields', [])}
            
            field_diff = {
                "object": obj_name,
                "fields_only_in_org1": list(set(fields1.keys()) - set(fields2.keys())),
                "fields_only_in_org2": list(set(fields2.keys()) - set(fields1.keys()))
            }
            
            if field_diff["fields_only_in_org1"] or field_diff["fields_only_in_org2"]:
                differences.append(field_diff)
        
        return {
            "objects_only_in_org1": list(only_in_org1),
            "objects_only_in_org2": list(only_in_org2),
            "common_objects_count": len(common_objects),
            "field_differences": differences
        }
    
    async def run_report_across_orgs(self, query: str) -> Dict[str, Any]:
        """
        Run the same query across all configured orgs.
        
        Useful for:
        - Consolidated reporting
        - Data quality checks
        - Cross-org analytics
        """
        results = {}
        
        for org_name in self.server.orgs.keys():
            try:
                print(f"Running query in {org_name}...")
                client = await self.server._get_client(org_name)
                result = await self.server._execute_tool(
                    "salesforce_query",
                    {"query": query},
                    client
                )
                
                results[org_name] = {
                    "success": True,
                    "total_size": result.get("totalSize", 0),
                    "records": result.get("records", [])
                }
            except Exception as e:
                results[org_name] = {
                    "success": False,
                    "error": str(e)
                }
        
        return results


async def demonstrate_multi_org_operations():
    """Demonstrate multi-org operations."""
    manager = MultiOrgSalesforceManager()
    
    print("Multi-Org Salesforce Management Demo")
    print("=" * 60)
    print()
    
    # Check available orgs
    print("Available Organizations:")
    for org_name in manager.server.orgs.keys():
        print(f"- {org_name}")
    print()
    
    # Example 1: Run report across all orgs
    print("Example 1: Account Count Across All Orgs")
    print("-" * 40)
    
    cross_org_results = await manager.run_report_across_orgs(
        "SELECT COUNT(Id) total FROM Account"
    )
    
    for org, result in cross_org_results.items():
        if result["success"]:
            total = result["records"][0]["total"] if result["records"] else 0
            print(f"{org}: {total} accounts")
        else:
            print(f"{org}: Error - {result['error']}")
    print()
    
    # Example 2: Compare schemas (if multiple orgs available)
    if len(manager.server.orgs) >= 2:
        org_names = list(manager.server.orgs.keys())
        print(f"Example 2: Schema Comparison between {org_names[0]} and {org_names[1]}")
        print("-" * 40)
        
        comparison = await manager.compare_org_schemas(org_names[0], org_names[1])
        
        print(f"Objects only in {org_names[0]}: {len(comparison['objects_only_in_org1'])}")
        print(f"Objects only in {org_names[1]}: {len(comparison['objects_only_in_org2'])}")
        print(f"Common objects: {comparison['common_objects_count']}")
        
        if comparison['field_differences']:
            print("\nField differences in common objects:")
            for diff in comparison['field_differences'][:3]:  # Show first 3
                print(f"- {diff['object']}:")
                if diff['fields_only_in_org1']:
                    print(f"  Fields only in {org_names[0]}: {', '.join(diff['fields_only_in_org1'][:5])}")
                if diff['fields_only_in_org2']:
                    print(f"  Fields only in {org_names[1]}: {', '.join(diff['fields_only_in_org2'][:5])}")
    
    # Example 3: Data quality check across orgs
    print("\nExample 3: Data Quality Check - Contacts Without Email")
    print("-" * 40)
    
    quality_check_results = await manager.run_report_across_orgs(
        "SELECT COUNT(Id) total FROM Contact WHERE Email = null"
    )
    
    for org, result in quality_check_results.items():
        if result["success"]:
            total = result["records"][0]["total"] if result["records"] else 0
            print(f"{org}: {total} contacts without email")
        else:
            print(f"{org}: Error - {result['error']}")
    
    # Example 4: Org-specific operations
    print("\nExample 4: Org-Specific Operations")
    print("-" * 40)
    
    for org_name in list(manager.server.orgs.keys())[:2]:  # First 2 orgs
        print(f"\nOperating on {org_name}:")
        
        try:
            client = await manager.server._get_client(org_name)
            
            # Get org limits
            # Note: This would require additional API implementation
            print(f"- Checking API limits...")
            
            # Get recent users
            user_result = await manager.server._execute_tool(
                "salesforce_query",
                {"query": "SELECT Id, Name, LastLoginDate FROM User WHERE IsActive = true ORDER BY LastLoginDate DESC LIMIT 5"},
                client
            )
            
            print(f"- Recently active users: {user_result.get('totalSize', 0)}")
            
        except Exception as e:
            print(f"- Error: {str(e)}")


def create_multi_org_config_example():
    """Generate example configuration for multi-org setup."""
    
    config_example = """
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

# Client-Specific Organization (Custom Domain)
SALESFORCE_CLIENT_ACME_USERNAME=integration@acme.com
SALESFORCE_CLIENT_ACME_PASSWORD=acmePassword123
SALESFORCE_CLIENT_ACME_SECURITY_TOKEN=acmeSecurityToken
SALESFORCE_CLIENT_ACME_DOMAIN=acme.my

# OAuth Configuration (Alternative to username/password)
SALESFORCE_OAUTH_CLIENT_ID=yourConnectedAppClientId
SALESFORCE_OAUTH_CLIENT_SECRET=yourConnectedAppClientSecret
SALESFORCE_OAUTH_REDIRECT_URI=http://localhost:8080/callback
"""
    
    return config_example


if __name__ == "__main__":
    # Show configuration example
    print("Multi-Org Configuration Example")
    print("=" * 60)
    print(create_multi_org_config_example())
    print()
    
    # Check if at least one org is configured
    has_config = any([
        os.getenv("SALESFORCE_USERNAME"),
        os.getenv("SALESFORCE_PROD_USERNAME"),
        os.getenv("SALESFORCE_SANDBOX_USERNAME"),
        os.getenv("SALESFORCE_DEV_USERNAME")
    ])
    
    if not has_config:
        print("Error: No Salesforce organizations configured.")
        print("Please set environment variables for at least one organization.")
        exit(1)
    
    # Run the demo
    asyncio.run(demonstrate_multi_org_operations())