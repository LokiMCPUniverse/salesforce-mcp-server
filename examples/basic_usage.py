"""Basic usage example for Salesforce MCP Server."""

import asyncio
import os
from salesforce_mcp import SalesforceMCPServer, SalesforceConfig

async def main():
    """Demonstrate basic Salesforce MCP operations."""
    
    # Initialize configuration
    # You can either use environment variables or pass configuration directly
    config = SalesforceConfig()
    
    # Create server instance
    server = SalesforceMCPServer(config)
    
    # Note: In actual MCP usage, the server communicates via stdio
    # This example shows direct method calls for demonstration
    
    # Example 1: Query records
    print("Example 1: Querying Accounts")
    print("-" * 50)
    query_result = await server._execute_tool(
        "salesforce_query",
        {"query": "SELECT Id, Name, Industry FROM Account LIMIT 5"},
        await server._get_client("default")
    )
    print(f"Found {query_result.get('totalSize', 0)} accounts")
    for record in query_result.get('records', []):
        print(f"- {record['Name']} ({record.get('Industry', 'N/A')})")
    print()
    
    # Example 2: Create a contact
    print("Example 2: Creating a Contact")
    print("-" * 50)
    create_result = await server._execute_tool(
        "salesforce_create_record",
        {
            "object_type": "Contact",
            "data": {
                "FirstName": "John",
                "LastName": "Doe",
                "Email": "john.doe@example.com",
                "Title": "Software Engineer"
            }
        },
        await server._get_client("default")
    )
    contact_id = create_result.get('id')
    print(f"Created contact with ID: {contact_id}")
    print()
    
    # Example 3: Update the contact
    if contact_id:
        print("Example 3: Updating the Contact")
        print("-" * 50)
        update_result = await server._execute_tool(
            "salesforce_update_record",
            {
                "object_type": "Contact",
                "record_id": contact_id,
                "data": {
                    "Title": "Senior Software Engineer",
                    "Department": "Engineering"
                }
            },
            await server._get_client("default")
        )
        print("Contact updated successfully")
        print()
        
        # Example 4: Get the updated contact
        print("Example 4: Retrieving the Updated Contact")
        print("-" * 50)
        get_result = await server._execute_tool(
            "salesforce_get_record",
            {
                "object_type": "Contact",
                "record_id": contact_id,
                "fields": ["FirstName", "LastName", "Email", "Title", "Department"]
            },
            await server._get_client("default")
        )
        print(f"Contact details:")
        print(f"- Name: {get_result['FirstName']} {get_result['LastName']}")
        print(f"- Email: {get_result['Email']}")
        print(f"- Title: {get_result['Title']}")
        print(f"- Department: {get_result.get('Department', 'N/A')}")
        print()
    
    # Example 5: List available objects
    print("Example 5: Listing Available Objects")
    print("-" * 50)
    objects_result = await server._execute_tool(
        "salesforce_list_objects",
        {},
        await server._get_client("default")
    )
    print(f"Found {len(objects_result['objects'])} objects")
    # Show first 10 objects
    for obj in objects_result['objects'][:10]:
        custom_indicator = " (Custom)" if obj['custom'] else ""
        print(f"- {obj['name']}: {obj['label']}{custom_indicator}")
    print("...")
    print()
    
    # Example 6: Describe an object
    print("Example 6: Describing the Contact Object")
    print("-" * 50)
    describe_result = await server._execute_tool(
        "salesforce_describe_object",
        {"object_type": "Contact"},
        await server._get_client("default")
    )
    print(f"Contact object has {len(describe_result.get('fields', []))} fields")
    print("Some important fields:")
    important_fields = ['Id', 'FirstName', 'LastName', 'Email', 'Phone', 'AccountId']
    for field in describe_result.get('fields', []):
        if field['name'] in important_fields:
            print(f"- {field['name']} ({field['type']}): {field['label']}")
    print()
    
    # Example 7: Execute SOQL with relationship
    print("Example 7: Query with Relationships")
    print("-" * 50)
    relationship_result = await server._execute_tool(
        "salesforce_query",
        {
            "query": """
                SELECT Id, Name, Email, Account.Name, Account.Industry 
                FROM Contact 
                WHERE Account.Name != null 
                LIMIT 5
            """
        },
        await server._get_client("default")
    )
    print(f"Contacts with accounts:")
    for contact in relationship_result.get('records', []):
        account_name = contact.get('Account', {}).get('Name', 'N/A') if contact.get('Account') else 'N/A'
        print(f"- {contact.get('Name', 'N/A')} works at {account_name}")
    
    # Cleanup: Delete the test contact if created
    if contact_id:
        print("\nCleaning up: Deleting test contact")
        await server._execute_tool(
            "salesforce_delete_record",
            {
                "object_type": "Contact",
                "record_id": contact_id
            },
            await server._get_client("default")
        )
        print("Test contact deleted")


if __name__ == "__main__":
    # Check for required environment variables
    required_vars = ["SALESFORCE_USERNAME", "SALESFORCE_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these environment variables and try again.")
        exit(1)
    
    # Run the examples
    asyncio.run(main())