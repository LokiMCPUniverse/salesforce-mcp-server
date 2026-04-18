"""Basic usage example for the Salesforce MCP Server.

This example exercises the underlying `SalesforceClient` directly. The MCP
server's tools are thin wrappers over this client, so anything you can do
here you can do through the `salesforce_*` tools.
"""

import asyncio
import os

from salesforce_mcp import SalesforceConfig
from salesforce_mcp.client import create_client_from_config


async def main() -> None:
    """Demonstrate basic Salesforce operations against the default org."""
    config = SalesforceConfig()
    org_config = config.get_org_config()
    client = create_client_from_config(org_config, config.get_rate_limit_config())

    async with client:
        # Example 1: Query records
        print("Example 1: Querying Accounts")
        print("-" * 50)
        query_result = await client.query(
            "SELECT Id, Name, Industry FROM Account LIMIT 5"
        )
        print(f"Found {query_result.get('totalSize', 0)} accounts")
        for record in query_result.get("records", []):
            print(f"- {record['Name']} ({record.get('Industry', 'N/A')})")
        print()

        # Example 2: Create a contact
        print("Example 2: Creating a Contact")
        print("-" * 50)
        create_result = await client.create_record(
            "Contact",
            {
                "FirstName": "John",
                "LastName": "Doe",
                "Email": "john.doe@example.com",
                "Title": "Software Engineer",
            },
        )
        contact_id = create_result.get("id")
        print(f"Created contact with ID: {contact_id}")
        print()

        if contact_id:
            # Example 3: Update the contact
            print("Example 3: Updating the Contact")
            print("-" * 50)
            await client.update_record(
                "Contact",
                contact_id,
                {
                    "Title": "Senior Software Engineer",
                    "Department": "Engineering",
                },
            )
            print("Contact updated successfully")
            print()

            # Example 4: Get the updated contact
            print("Example 4: Retrieving the Updated Contact")
            print("-" * 50)
            get_result = await client.get_record(
                "Contact",
                contact_id,
                fields=["FirstName", "LastName", "Email", "Title", "Department"],
            )
            print("Contact details:")
            print(f"- Name: {get_result['FirstName']} {get_result['LastName']}")
            print(f"- Email: {get_result['Email']}")
            print(f"- Title: {get_result['Title']}")
            print(f"- Department: {get_result.get('Department', 'N/A')}")
            print()

        # Example 5: List available objects
        print("Example 5: Listing Available Objects")
        print("-" * 50)
        objects_result = await client.describe_global()
        sobjects = objects_result.get("sobjects", [])
        print(f"Found {len(sobjects)} objects")
        for obj in sobjects[:10]:
            custom = " (Custom)" if obj.get("custom") else ""
            print(f"- {obj['name']}: {obj['label']}{custom}")
        print("...")
        print()

        # Example 6: Describe an object
        print("Example 6: Describing the Contact Object")
        print("-" * 50)
        describe_result = await client.describe_object("Contact")
        print(f"Contact object has {len(describe_result.get('fields', []))} fields")
        important_fields = {"Id", "FirstName", "LastName", "Email", "Phone", "AccountId"}
        for field in describe_result.get("fields", []):
            if field["name"] in important_fields:
                print(f"- {field['name']} ({field['type']}): {field['label']}")
        print()

        # Example 7: Query with relationships
        print("Example 7: Query with Relationships")
        print("-" * 50)
        relationship_result = await client.query(
            """
            SELECT Id, Name, Email, Account.Name, Account.Industry
            FROM Contact
            WHERE Account.Name != null
            LIMIT 5
            """
        )
        print("Contacts with accounts:")
        for contact in relationship_result.get("records", []):
            account = contact.get("Account") or {}
            print(f"- {contact.get('Name', 'N/A')} works at {account.get('Name', 'N/A')}")

        # Cleanup
        if contact_id:
            print("\nCleaning up: Deleting test contact")
            await client.delete_record("Contact", contact_id)
            print("Test contact deleted")


if __name__ == "__main__":
    required_vars = ["SALESFORCE_USERNAME", "SALESFORCE_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these environment variables and try again.")
        raise SystemExit(1)

    asyncio.run(main())
