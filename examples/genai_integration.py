"""Example of integrating Salesforce MCP Server with GenAI applications."""

import asyncio
import json
from typing import Dict, Any, List
from salesforce_mcp import SalesforceMCPServer, SalesforceConfig


class SalesforceAIAssistant:
    """
    Example AI assistant that uses Salesforce MCP Server to help with CRM tasks.
    
    This demonstrates how to integrate the MCP server with a GenAI application
    for natural language interactions with Salesforce data.
    """
    
    def __init__(self, salesforce_server: SalesforceMCPServer):
        self.server = salesforce_server
        self.context = {}
    
    async def process_natural_language_query(self, user_input: str) -> Dict[str, Any]:
        """
        Process a natural language query and execute appropriate Salesforce operations.
        
        In a real implementation, this would use an LLM to understand intent
        and generate appropriate SOQL queries or operations.
        """
        # Simplified intent detection (in reality, use an LLM)
        user_input_lower = user_input.lower()
        
        if "find" in user_input_lower or "search" in user_input_lower:
            return await self._handle_search_query(user_input)
        elif "create" in user_input_lower or "add" in user_input_lower:
            return await self._handle_create_request(user_input)
        elif "update" in user_input_lower or "change" in user_input_lower:
            return await self._handle_update_request(user_input)
        elif "report" in user_input_lower or "summary" in user_input_lower:
            return await self._handle_report_request(user_input)
        else:
            return {"error": "Could not understand the request. Please be more specific."}
    
    async def _handle_search_query(self, query: str) -> Dict[str, Any]:
        """Handle search/find queries."""
        # Example: "Find all accounts in the technology industry"
        if "account" in query.lower() and "technology" in query.lower():
            soql = "SELECT Id, Name, Industry, AnnualRevenue FROM Account WHERE Industry = 'Technology' LIMIT 10"
        # Example: "Find contacts at Acme Corp"
        elif "contact" in query.lower() and "acme" in query.lower():
            soql = "SELECT Id, Name, Email, Title FROM Contact WHERE Account.Name LIKE '%Acme%' LIMIT 10"
        # Example: "Find open opportunities over 100k"
        elif "opportunities" in query.lower() and ("100k" in query.lower() or "100000" in query):
            soql = "SELECT Id, Name, Amount, StageName, CloseDate FROM Opportunity WHERE IsClosed = false AND Amount > 100000 ORDER BY Amount DESC LIMIT 10"
        else:
            # Generic search
            soql = "SELECT Id, Name FROM Account LIMIT 5"
        
        client = await self.server._get_client("default")
        result = await self.server._execute_tool(
            "salesforce_query",
            {"query": soql},
            client
        )
        
        return {
            "query": soql,
            "results": result.get("records", []),
            "total": result.get("totalSize", 0),
            "natural_response": self._format_search_results(result)
        }
    
    async def _handle_create_request(self, query: str) -> Dict[str, Any]:
        """Handle create/add requests."""
        # Simplified example - in reality, use NLP to extract entities
        if "contact" in query.lower():
            # Example: "Create a contact John Smith at john@example.com"
            data = {
                "FirstName": "John",
                "LastName": "Smith",
                "Email": "john.smith@example.com",
                "Title": "Manager"
            }
            object_type = "Contact"
        elif "account" in query.lower():
            # Example: "Create an account for Example Corp"
            data = {
                "Name": "Example Corp",
                "Industry": "Technology",
                "Type": "Prospect"
            }
            object_type = "Account"
        else:
            return {"error": "Could not determine what type of record to create"}
        
        client = await self.server._get_client("default")
        result = await self.server._execute_tool(
            "salesforce_create_record",
            {"object_type": object_type, "data": data},
            client
        )
        
        return {
            "action": "create",
            "object_type": object_type,
            "record_id": result.get("id"),
            "success": result.get("success", False),
            "natural_response": f"Successfully created {object_type} with ID: {result.get('id')}"
        }
    
    async def _handle_update_request(self, query: str) -> Dict[str, Any]:
        """Handle update/change requests."""
        # In a real implementation, extract the record ID and fields from the query
        # For demo, we'll update a specific field
        return {
            "action": "update",
            "natural_response": "To update a record, please provide the record ID and the fields to update."
        }
    
    async def _handle_report_request(self, query: str) -> Dict[str, Any]:
        """Handle report/summary requests."""
        client = await self.server._get_client("default")
        
        # Example: Generate a summary report
        summaries = []
        
        # Get account summary
        account_result = await self.server._execute_tool(
            "salesforce_query",
            {"query": "SELECT COUNT(Id) total, Industry FROM Account GROUP BY Industry"},
            client
        )
        summaries.append({
            "type": "Accounts by Industry",
            "data": account_result.get("records", [])
        })
        
        # Get opportunity pipeline
        opp_result = await self.server._execute_tool(
            "salesforce_query",
            {"query": "SELECT COUNT(Id) total, SUM(Amount) total_amount, StageName FROM Opportunity WHERE IsClosed = false GROUP BY StageName"},
            client
        )
        summaries.append({
            "type": "Open Opportunity Pipeline",
            "data": opp_result.get("records", [])
        })
        
        # Get recent activities
        activity_result = await self.server._execute_tool(
            "salesforce_query",
            {"query": "SELECT COUNT(Id) total FROM Task WHERE CreatedDate = THIS_WEEK"},
            client
        )
        summaries.append({
            "type": "Tasks Created This Week",
            "data": activity_result.get("records", [])
        })
        
        return {
            "action": "report",
            "summaries": summaries,
            "natural_response": self._format_report_summary(summaries)
        }
    
    def _format_search_results(self, result: Dict[str, Any]) -> str:
        """Format search results in natural language."""
        total = result.get("totalSize", 0)
        records = result.get("records", [])
        
        if total == 0:
            return "No records found matching your search criteria."
        
        response = f"Found {total} record(s). "
        if records:
            response += "Here are the results:\n"
            for i, record in enumerate(records[:5], 1):
                name = record.get("Name", "Unnamed")
                response += f"{i}. {name}"
                # Add additional context based on record type
                if "Email" in record:
                    response += f" ({record['Email']})"
                elif "Industry" in record:
                    response += f" - {record['Industry']}"
                elif "Amount" in record:
                    response += f" - ${record['Amount']:,.2f}"
                response += "\n"
        
        return response
    
    def _format_report_summary(self, summaries: List[Dict[str, Any]]) -> str:
        """Format report summaries in natural language."""
        response = "Here's your Salesforce summary:\n\n"
        
        for summary in summaries:
            response += f"**{summary['type']}**\n"
            for item in summary['data']:
                if 'Industry' in item:
                    response += f"- {item.get('Industry', 'Unknown')}: {item.get('total', 0)} accounts\n"
                elif 'StageName' in item:
                    total_amount = item.get('total_amount', 0)
                    response += f"- {item['StageName']}: {item.get('total', 0)} opportunities (${total_amount:,.2f})\n"
                else:
                    response += f"- Total: {item.get('total', 0)}\n"
            response += "\n"
        
        return response


async def demonstrate_ai_integration():
    """Demonstrate AI-powered Salesforce interactions."""
    # Initialize the server
    config = SalesforceConfig()
    server = SalesforceMCPServer(config)
    
    # Create AI assistant
    assistant = SalesforceAIAssistant(server)
    
    # Example queries that an AI might process
    example_queries = [
        "Find all accounts in the technology industry",
        "Search for contacts at Acme Corp",
        "Show me open opportunities over 100k",
        "Create a contact for John Smith at john@example.com",
        "Generate a summary report of our Salesforce data"
    ]
    
    print("Salesforce AI Assistant Demo")
    print("=" * 60)
    print()
    
    for query in example_queries:
        print(f"User: {query}")
        print("-" * 40)
        
        try:
            result = await assistant.process_natural_language_query(query)
            
            if "error" in result:
                print(f"Error: {result['error']}")
            else:
                print(f"Assistant: {result.get('natural_response', 'Processing complete.')}")
                
                # Show additional details for debugging
                if "query" in result:
                    print(f"\n[Debug] SOQL: {result['query']}")
                if "results" in result and result["results"]:
                    print(f"[Debug] Found {len(result['results'])} records")
            
        except Exception as e:
            print(f"Error processing query: {str(e)}")
        
        print("\n")


def create_genai_prompt_examples():
    """
    Generate example prompts for GenAI integration with Salesforce.
    
    These prompts can be used with LLMs to generate appropriate
    Salesforce MCP tool calls.
    """
    
    prompts = {
        "search_accounts": """
User wants to find technology companies with revenue over $1M.
Generate a Salesforce MCP tool call to search for these accounts.

Tool: salesforce_query
Expected output format:
{
    "tool": "salesforce_query",
    "arguments": {
        "query": "SELECT Id, Name, Industry, AnnualRevenue FROM Account WHERE Industry = 'Technology' AND AnnualRevenue > 1000000 ORDER BY AnnualRevenue DESC"
    }
}
""",
        
        "create_contact": """
User wants to create a new contact:
- Name: Sarah Johnson
- Email: sarah.johnson@techcorp.com
- Title: VP of Engineering
- Company: TechCorp (Account ID: 001XX000003DHPh)

Generate a Salesforce MCP tool call to create this contact.

Tool: salesforce_create_record
Expected output format:
{
    "tool": "salesforce_create_record",
    "arguments": {
        "object_type": "Contact",
        "data": {
            "FirstName": "Sarah",
            "LastName": "Johnson",
            "Email": "sarah.johnson@techcorp.com",
            "Title": "VP of Engineering",
            "AccountId": "001XX000003DHPh"
        }
    }
}
""",
        
        "update_opportunity": """
User wants to update an opportunity to move it to the next stage.
Opportunity ID: 006XX000003DHPz
Current Stage: Qualification
Next Stage: Proposal/Price Quote

Generate a Salesforce MCP tool call to update this opportunity.

Tool: salesforce_update_record
Expected output format:
{
    "tool": "salesforce_update_record",
    "arguments": {
        "object_type": "Opportunity",
        "record_id": "006XX000003DHPz",
        "data": {
            "StageName": "Proposal/Price Quote"
        }
    }
}
""",
        
        "bulk_import": """
User wants to import a list of contacts from a CSV file.
The contacts should be created in bulk for better performance.

Generate a Salesforce MCP tool call for bulk contact creation.

Tool: salesforce_bulk_create
Expected output format:
{
    "tool": "salesforce_bulk_create",
    "arguments": {
        "object_type": "Contact",
        "records": [
            {
                "FirstName": "John",
                "LastName": "Doe",
                "Email": "john.doe@example.com"
            },
            {
                "FirstName": "Jane",
                "LastName": "Smith",
                "Email": "jane.smith@example.com"
            }
        ],
        "batch_size": 200
    }
}
"""
    }
    
    return prompts


if __name__ == "__main__":
    import os
    
    # Check for required environment variables
    required_vars = ["SALESFORCE_USERNAME", "SALESFORCE_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these environment variables and try again.")
        exit(1)
    
    # Run the AI integration demo
    asyncio.run(demonstrate_ai_integration())
    
    # Show prompt examples
    print("\n" + "=" * 60)
    print("GenAI Prompt Examples")
    print("=" * 60)
    prompts = create_genai_prompt_examples()
    for name, prompt in prompts.items():
        print(f"\n### {name.replace('_', ' ').title()}")
        print(prompt)