"""Example of handling large data volumes with Salesforce Bulk API."""

import asyncio
import csv
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta
from salesforce_mcp import SalesforceMCPServer, SalesforceConfig


class BulkDataProcessor:
    """
    Handles large-scale data operations with Salesforce.
    
    Use cases:
    - Data migration
    - Mass updates
    - Large data imports/exports
    - Data cleansing operations
    """
    
    def __init__(self, server: SalesforceMCPServer):
        self.server = server
    
    async def bulk_import_contacts(self, csv_file_path: str) -> Dict[str, Any]:
        """
        Import contacts from a CSV file using Bulk API.
        
        Args:
            csv_file_path: Path to CSV file containing contact data
            
        Returns:
            Summary of the import operation
        """
        print(f"Importing contacts from {csv_file_path}")
        
        # Read CSV file
        contacts = []
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Map CSV columns to Salesforce fields
                contact = {
                    "FirstName": row.get("first_name", ""),
                    "LastName": row.get("last_name", ""),
                    "Email": row.get("email", ""),
                    "Phone": row.get("phone", ""),
                    "Title": row.get("title", ""),
                    "Department": row.get("department", ""),
                    "MailingStreet": row.get("street", ""),
                    "MailingCity": row.get("city", ""),
                    "MailingState": row.get("state", ""),
                    "MailingPostalCode": row.get("zip", ""),
                    "MailingCountry": row.get("country", "USA")
                }
                
                # Remove empty fields
                contact = {k: v for k, v in contact.items() if v}
                contacts.append(contact)
        
        print(f"Read {len(contacts)} contacts from CSV")
        
        # Import using bulk API
        client = await self.server._get_client("default")
        result = await self.server._execute_tool(
            "salesforce_bulk_create",
            {
                "object_type": "Contact",
                "records": contacts,
                "batch_size": 200  # Salesforce recommended batch size
            },
            client
        )
        
        return {
            "total_records": len(contacts),
            "processed": result.get("records_processed", 0),
            "failed": result.get("records_failed", 0),
            "job_id": result.get("job_id"),
            "success_rate": (result.get("records_processed", 0) - result.get("records_failed", 0)) / len(contacts) * 100 if contacts else 0
        }
    
    async def mass_update_field(
        self,
        object_type: str,
        filter_query: str,
        field_updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Mass update a field for all records matching a query.
        
        Args:
            object_type: Salesforce object type
            filter_query: SOQL query to find records to update
            field_updates: Dictionary of field names and new values
            
        Returns:
            Summary of the update operation
        """
        print(f"Mass updating {object_type} records")
        
        # First, get all record IDs that need updating
        client = await self.server._get_client("default")
        
        # Build query to get IDs
        id_query = filter_query
        if "SELECT" in id_query.upper():
            # Ensure Id is in the query
            if "Id" not in id_query:
                id_query = id_query.replace("SELECT", "SELECT Id,", 1)
        else:
            # If no SELECT clause, create one
            id_query = f"SELECT Id FROM {object_type} WHERE {filter_query}"
        
        query_result = await self.server._execute_tool(
            "salesforce_query",
            {"query": id_query},
            client
        )
        
        records = query_result.get("records", [])
        print(f"Found {len(records)} records to update")
        
        if not records:
            return {"updated": 0, "failed": 0, "message": "No records found to update"}
        
        # Prepare records for bulk update
        update_records = []
        for record in records:
            update_record = {"Id": record["Id"]}
            update_record.update(field_updates)
            update_records.append(update_record)
        
        # Use bulk API for update (would need to implement bulk update in client)
        # For now, we'll demonstrate with individual updates (not recommended for large volumes)
        updated = 0
        failed = 0
        
        # In production, use bulk update API
        # This is just for demonstration
        for i, record in enumerate(update_records[:10]):  # Limit to 10 for demo
            try:
                await self.server._execute_tool(
                    "salesforce_update_record",
                    {
                        "object_type": object_type,
                        "record_id": record["Id"],
                        "data": {k: v for k, v in record.items() if k != "Id"}
                    },
                    client
                )
                updated += 1
                
                if (i + 1) % 10 == 0:
                    print(f"Updated {i + 1} records...")
                    
            except Exception as e:
                failed += 1
                print(f"Failed to update record {record['Id']}: {str(e)}")
        
        return {
            "total_records": len(records),
            "updated": updated,
            "failed": failed,
            "message": f"Mass update completed for {object_type}"
        }
    
    async def export_large_dataset(
        self,
        query: str,
        output_file: str,
        batch_size: int = 2000
    ) -> Dict[str, Any]:
        """
        Export large dataset to CSV file using query batching.
        
        Args:
            query: SOQL query to export data
            output_file: Path to output CSV file
            batch_size: Number of records per batch
            
        Returns:
            Summary of the export operation
        """
        print(f"Exporting data to {output_file}")
        
        client = await self.server._get_client("default")
        
        # Get total count first
        count_query = query.replace("SELECT", "SELECT COUNT()", 1)
        count_query = count_query.split("FROM")[0] + " FROM" + count_query.split("FROM")[1].split("ORDER BY")[0]
        
        count_result = await self.server._execute_tool(
            "salesforce_query",
            {"query": count_query},
            client
        )
        
        total_count = count_result.get("totalSize", 0)
        print(f"Total records to export: {total_count}")
        
        # Export in batches
        exported = 0
        offset = 0
        first_batch = True
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = None
            
            while offset < total_count:
                # Add LIMIT and OFFSET to query
                batch_query = f"{query} LIMIT {batch_size} OFFSET {offset}"
                
                batch_result = await self.server._execute_tool(
                    "salesforce_query",
                    {"query": batch_query},
                    client
                )
                
                records = batch_result.get("records", [])
                
                if records:
                    # Initialize CSV writer with headers from first batch
                    if first_batch:
                        # Get field names from first record
                        fieldnames = [k for k in records[0].keys() if not k.startswith("attributes")]
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        first_batch = False
                    
                    # Write records
                    for record in records:
                        # Remove attributes field
                        clean_record = {k: v for k, v in record.items() if not k.startswith("attributes")}
                        writer.writerow(clean_record)
                    
                    exported += len(records)
                    print(f"Exported {exported}/{total_count} records...")
                
                offset += batch_size
                
                # Add small delay to avoid rate limits
                await asyncio.sleep(0.1)
        
        return {
            "total_records": total_count,
            "exported": exported,
            "output_file": output_file,
            "success": exported == total_count
        }
    
    async def data_cleansing_operation(
        self,
        object_type: str,
        cleansing_rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Perform data cleansing operations on Salesforce data.
        
        Args:
            object_type: Salesforce object type
            cleansing_rules: List of cleansing rules to apply
            
        Returns:
            Summary of cleansing operations
        """
        print(f"Performing data cleansing on {object_type}")
        
        client = await self.server._get_client("default")
        results = []
        
        for rule in cleansing_rules:
            rule_name = rule.get("name", "Unknown rule")
            print(f"\nApplying rule: {rule_name}")
            
            # Find records that need cleansing
            find_query = rule.get("find_query")
            if not find_query:
                continue
            
            query_result = await self.server._execute_tool(
                "salesforce_query",
                {"query": find_query},
                client
            )
            
            records = query_result.get("records", [])
            print(f"Found {len(records)} records matching rule criteria")
            
            # Apply cleansing action
            action = rule.get("action")
            cleansed = 0
            failed = 0
            
            if action == "update":
                updates = rule.get("updates", {})
                for record in records[:10]:  # Limit for demo
                    try:
                        await self.server._execute_tool(
                            "salesforce_update_record",
                            {
                                "object_type": object_type,
                                "record_id": record["Id"],
                                "data": updates
                            },
                            client
                        )
                        cleansed += 1
                    except Exception as e:
                        failed += 1
                        print(f"Failed to cleanse record {record['Id']}: {str(e)}")
            
            elif action == "delete":
                for record in records[:5]:  # Limit for demo, be careful with deletes!
                    try:
                        await self.server._execute_tool(
                            "salesforce_delete_record",
                            {
                                "object_type": object_type,
                                "record_id": record["Id"]
                            },
                            client
                        )
                        cleansed += 1
                    except Exception as e:
                        failed += 1
                        print(f"Failed to delete record {record['Id']}: {str(e)}")
            
            results.append({
                "rule": rule_name,
                "records_found": len(records),
                "cleansed": cleansed,
                "failed": failed
            })
        
        return {
            "rules_applied": len(cleansing_rules),
            "results": results,
            "total_cleansed": sum(r["cleansed"] for r in results),
            "total_failed": sum(r["failed"] for r in results)
        }


def generate_sample_csv(file_path: str, num_records: int = 100):
    """Generate a sample CSV file for testing bulk import."""
    
    sample_data = []
    for i in range(num_records):
        sample_data.append({
            "first_name": f"Test{i}",
            "last_name": f"User{i}",
            "email": f"test.user{i}@example.com",
            "phone": f"555-{i:04d}",
            "title": ["Manager", "Developer", "Analyst", "Director"][i % 4],
            "department": ["Sales", "Engineering", "Marketing", "Finance"][i % 4],
            "city": ["New York", "San Francisco", "Chicago", "Boston"][i % 4],
            "state": ["NY", "CA", "IL", "MA"][i % 4],
            "country": "USA"
        })
    
    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = sample_data[0].keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_data)
    
    print(f"Generated sample CSV with {num_records} records at {file_path}")


async def demonstrate_bulk_operations():
    """Demonstrate bulk operations with Salesforce."""
    
    # Initialize server
    config = SalesforceConfig()
    server = SalesforceMCPServer(config)
    processor = BulkDataProcessor(server)
    
    print("Salesforce Bulk Operations Demo")
    print("=" * 60)
    print()
    
    # Example 1: Export data
    print("Example 1: Exporting Account Data")
    print("-" * 40)
    
    export_result = await processor.export_large_dataset(
        query="SELECT Id, Name, Industry, AnnualRevenue, NumberOfEmployees FROM Account",
        output_file="accounts_export.csv",
        batch_size=500
    )
    
    print(f"Export completed: {export_result['exported']} records exported to {export_result['output_file']}")
    print()
    
    # Example 2: Mass update
    print("Example 2: Mass Update Operation")
    print("-" * 40)
    
    # Update all accounts in Technology industry to have a specific type
    update_result = await processor.mass_update_field(
        object_type="Account",
        filter_query="Industry = 'Technology' AND Type = null",
        field_updates={
            "Type": "Technology Partner",
            "CustomerPriority__c": "High"
        }
    )
    
    print(f"Mass update completed: {update_result['updated']} records updated")
    print()
    
    # Example 3: Data cleansing
    print("Example 3: Data Cleansing")
    print("-" * 40)
    
    cleansing_rules = [
        {
            "name": "Standardize phone numbers",
            "find_query": "SELECT Id, Phone FROM Contact WHERE Phone != null AND (NOT Phone LIKE '+%')",
            "action": "update",
            "updates": {"Description": "Phone number needs standardization"}
        },
        {
            "name": "Flag incomplete contacts",
            "find_query": "SELECT Id FROM Contact WHERE Email = null AND Phone = null",
            "action": "update",
            "updates": {"Data_Quality_Score__c": "Low", "Needs_Review__c": True}
        },
        {
            "name": "Remove test accounts",
            "find_query": "SELECT Id FROM Account WHERE Name LIKE '%TEST%' OR Name LIKE '%test%'",
            "action": "delete"  # Be very careful with delete operations!
        }
    ]
    
    cleansing_result = await processor.data_cleansing_operation(
        object_type="Contact",
        cleansing_rules=cleansing_rules[:2]  # Skip delete rule for safety
    )
    
    print(f"Data cleansing completed:")
    for result in cleansing_result['results']:
        print(f"- {result['rule']}: {result['cleansed']} records cleansed")
    print()
    
    # Example 4: Bulk import (if CSV exists)
    print("Example 4: Bulk Import")
    print("-" * 40)
    
    sample_csv = "sample_contacts.csv"
    generate_sample_csv(sample_csv, num_records=50)
    
    import_result = await processor.bulk_import_contacts(sample_csv)
    
    print(f"Import completed:")
    print(f"- Total records: {import_result['total_records']}")
    print(f"- Processed: {import_result['processed']}")
    print(f"- Failed: {import_result['failed']}")
    print(f"- Success rate: {import_result['success_rate']:.1f}%")
    
    # Cleanup
    import os
    if os.path.exists(sample_csv):
        os.remove(sample_csv)
    if os.path.exists("accounts_export.csv"):
        os.remove("accounts_export.csv")


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
    
    # Run the bulk operations demo
    asyncio.run(demonstrate_bulk_operations())