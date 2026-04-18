"""Example of integrating the Salesforce MCP Server with GenAI applications."""

import asyncio
import os
from typing import Any

from salesforce_mcp import SalesforceConfig
from salesforce_mcp.client import SalesforceClient, create_client_from_config


class SalesforceAIAssistant:
    """Minimal AI-style assistant that dispatches user intent to Salesforce operations.

    In a real integration, intent classification and argument extraction would
    be performed by an LLM; here we use keyword matching for illustration.
    """

    def __init__(self, client: SalesforceClient) -> None:
        self.client = client

    async def process_natural_language_query(self, user_input: str) -> dict[str, Any]:
        text = user_input.lower()
        if "find" in text or "search" in text:
            return await self._handle_search_query(user_input)
        if "create" in text or "add" in text:
            return await self._handle_create_request(user_input)
        if "update" in text or "change" in text:
            return {
                "action": "update",
                "natural_response": "To update a record, please provide the record ID and fields.",
            }
        if "report" in text or "summary" in text:
            return await self._handle_report_request()
        return {"error": "Could not understand the request."}

    async def _handle_search_query(self, query: str) -> dict[str, Any]:
        q = query.lower()
        if "account" in q and "technology" in q:
            soql = (
                "SELECT Id, Name, Industry, AnnualRevenue FROM Account "
                "WHERE Industry = 'Technology' LIMIT 10"
            )
        elif "contact" in q and "acme" in q:
            soql = (
                "SELECT Id, Name, Email, Title FROM Contact "
                "WHERE Account.Name LIKE '%Acme%' LIMIT 10"
            )
        elif "opportunities" in q and ("100k" in q or "100000" in q):
            soql = (
                "SELECT Id, Name, Amount, StageName, CloseDate FROM Opportunity "
                "WHERE IsClosed = false AND Amount > 100000 ORDER BY Amount DESC LIMIT 10"
            )
        else:
            soql = "SELECT Id, Name FROM Account LIMIT 5"

        result = await self.client.query(soql)
        return {
            "query": soql,
            "results": result.get("records", []),
            "total": result.get("totalSize", 0),
            "natural_response": self._format_search_results(result),
        }

    async def _handle_create_request(self, query: str) -> dict[str, Any]:
        if "contact" in query.lower():
            object_type = "Contact"
            data = {
                "FirstName": "John",
                "LastName": "Smith",
                "Email": "john.smith@example.com",
                "Title": "Manager",
            }
        elif "account" in query.lower():
            object_type = "Account"
            data = {"Name": "Example Corp", "Industry": "Technology", "Type": "Prospect"}
        else:
            return {"error": "Could not determine what type of record to create"}

        result = await self.client.create_record(object_type, data)
        return {
            "action": "create",
            "object_type": object_type,
            "record_id": result.get("id"),
            "success": result.get("success", False),
            "natural_response": f"Created {object_type} with ID: {result.get('id')}",
        }

    async def _handle_report_request(self) -> dict[str, Any]:
        summaries: list[dict[str, Any]] = []
        summaries.append(
            {
                "type": "Accounts by Industry",
                "data": (
                    await self.client.query(
                        "SELECT COUNT(Id) total, Industry FROM Account GROUP BY Industry"
                    )
                ).get("records", []),
            }
        )
        summaries.append(
            {
                "type": "Open Opportunity Pipeline",
                "data": (
                    await self.client.query(
                        "SELECT COUNT(Id) total, SUM(Amount) total_amount, StageName "
                        "FROM Opportunity WHERE IsClosed = false GROUP BY StageName"
                    )
                ).get("records", []),
            }
        )
        summaries.append(
            {
                "type": "Tasks Created This Week",
                "data": (
                    await self.client.query(
                        "SELECT COUNT(Id) total FROM Task WHERE CreatedDate = THIS_WEEK"
                    )
                ).get("records", []),
            }
        )
        return {
            "action": "report",
            "summaries": summaries,
            "natural_response": self._format_report_summary(summaries),
        }

    @staticmethod
    def _format_search_results(result: dict[str, Any]) -> str:
        total = result.get("totalSize", 0)
        records = result.get("records", [])
        if total == 0:
            return "No records found."
        response = f"Found {total} record(s).\n"
        for i, record in enumerate(records[:5], 1):
            name = record.get("Name", "Unnamed")
            line = f"{i}. {name}"
            if "Email" in record:
                line += f" ({record['Email']})"
            elif "Industry" in record:
                line += f" - {record['Industry']}"
            elif "Amount" in record:
                line += f" - ${record['Amount']:,.2f}"
            response += line + "\n"
        return response

    @staticmethod
    def _format_report_summary(summaries: list[dict[str, Any]]) -> str:
        response = "Salesforce summary:\n\n"
        for summary in summaries:
            response += f"**{summary['type']}**\n"
            for item in summary["data"]:
                if "Industry" in item:
                    response += f"- {item.get('Industry', 'Unknown')}: {item.get('total', 0)} accounts\n"
                elif "StageName" in item:
                    response += (
                        f"- {item['StageName']}: {item.get('total', 0)} opportunities "
                        f"(${item.get('total_amount', 0):,.2f})\n"
                    )
                else:
                    response += f"- Total: {item.get('total', 0)}\n"
            response += "\n"
        return response


async def demonstrate_ai_integration() -> None:
    config = SalesforceConfig()
    client = create_client_from_config(config.get_org_config(), config.get_rate_limit_config())

    async with client:
        assistant = SalesforceAIAssistant(client)
        example_queries = [
            "Find all accounts in the technology industry",
            "Search for contacts at Acme Corp",
            "Show me open opportunities over 100k",
            "Create a contact for John Smith at john@example.com",
            "Generate a summary report of our Salesforce data",
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
            except Exception as exc:
                print(f"Error processing query: {exc}")
            print()


def create_genai_prompt_examples() -> dict[str, str]:
    """Return example prompts that an LLM can translate into MCP tool calls."""
    return {
        "search_accounts": (
            "Call the salesforce_query tool with "
            "\"SELECT Id, Name, Industry, AnnualRevenue FROM Account "
            "WHERE Industry = 'Technology' AND AnnualRevenue > 1000000 "
            "ORDER BY AnnualRevenue DESC\""
        ),
        "create_contact": (
            "Call the salesforce_create_record tool with object_type='Contact' and "
            "data={'FirstName': 'Sarah', 'LastName': 'Johnson', "
            "'Email': 'sarah@techcorp.com', 'AccountId': '001XX000003DHPh'}"
        ),
        "update_opportunity": (
            "Call the salesforce_update_record tool with object_type='Opportunity', "
            "record_id='006XX000003DHPz', data={'StageName': 'Proposal/Price Quote'}"
        ),
        "bulk_import": (
            "Call the salesforce_bulk_create tool with object_type='Contact' and a list "
            "of Contact records; use batch_size=200 for efficient loading."
        ),
    }


if __name__ == "__main__":
    required_vars = ["SALESFORCE_USERNAME", "SALESFORCE_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print("Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        raise SystemExit(1)

    asyncio.run(demonstrate_ai_integration())
    print("\n" + "=" * 60)
    print("GenAI Prompt Examples")
    print("=" * 60)
    for name, prompt in create_genai_prompt_examples().items():
        print(f"\n### {name.replace('_', ' ').title()}")
        print(prompt)
