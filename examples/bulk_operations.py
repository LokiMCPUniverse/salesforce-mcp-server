"""Example of handling large data volumes with the Salesforce Bulk API."""

import asyncio
import csv
import os
from typing import Any

from salesforce_mcp import SalesforceConfig
from salesforce_mcp.client import SalesforceClient, create_client_from_config


class BulkDataProcessor:
    """Handles large-scale data operations with Salesforce."""

    def __init__(self, client: SalesforceClient) -> None:
        self.client = client

    async def bulk_import_contacts(self, csv_file_path: str) -> dict[str, Any]:
        """Import contacts from a CSV file via Bulk API 2.0."""
        print(f"Importing contacts from {csv_file_path}")

        contacts: list[dict[str, Any]] = []
        with open(csv_file_path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
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
                    "MailingCountry": row.get("country", "USA"),
                }
                contacts.append({k: v for k, v in contact.items() if v})

        print(f"Read {len(contacts)} contacts from CSV")
        result = await self.client.bulk_create("Contact", contacts, batch_size=200)
        processed = result.get("numberRecordsProcessed", 0)
        failed = result.get("numberRecordsFailed", 0)
        return {
            "total_records": len(contacts),
            "processed": processed,
            "failed": failed,
            "job_id": result.get("id"),
            "success_rate": ((processed - failed) / len(contacts) * 100) if contacts else 0,
        }

    async def mass_update_field(
        self,
        object_type: str,
        filter_query: str,
        field_updates: dict[str, Any],
        max_records: int = 10,
    ) -> dict[str, Any]:
        """Mass update records matching a SOQL filter (limited to ``max_records``)."""
        if "SELECT" in filter_query.upper():
            id_query = filter_query if "Id" in filter_query else filter_query.replace("SELECT", "SELECT Id,", 1)
        else:
            id_query = f"SELECT Id FROM {object_type} WHERE {filter_query}"

        query_result = await self.client.query(id_query)
        records = query_result.get("records", [])
        print(f"Found {len(records)} records to update")
        if not records:
            return {"updated": 0, "failed": 0, "message": "No records found to update"}

        updated = 0
        failed = 0
        for record in records[:max_records]:
            try:
                await self.client.update_record(object_type, record["Id"], field_updates)
                updated += 1
            except Exception as exc:
                failed += 1
                print(f"Failed to update record {record['Id']}: {exc}")

        return {
            "total_records": len(records),
            "updated": updated,
            "failed": failed,
            "message": f"Mass update completed for {object_type}",
        }

    async def export_large_dataset(
        self,
        query: str,
        output_file: str,
        batch_size: int = 2000,
    ) -> dict[str, Any]:
        """Paginate a SOQL query and write the rows to ``output_file`` (CSV)."""
        print(f"Exporting data to {output_file}")

        exported = 0
        total_size = 0
        next_url: str | None = None
        first_batch = True

        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            writer: csv.DictWriter | None = None
            while True:
                if next_url is None:
                    batch = await self.client.query(f"{query} LIMIT {batch_size}")
                    total_size = batch.get("totalSize", 0)
                else:
                    batch = await self.client.query_more(next_url)

                records = batch.get("records", [])
                if records:
                    if first_batch and writer is None:
                        fieldnames = [k for k in records[0] if k != "attributes"]
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        first_batch = False
                    for record in records:
                        clean = {k: v for k, v in record.items() if k != "attributes"}
                        writer.writerow(clean)
                    exported += len(records)
                    print(f"Exported {exported} records...")

                if batch.get("done", True):
                    break
                next_url = batch.get("nextRecordsUrl")
                if not next_url:
                    break

        return {
            "total_records": total_size,
            "exported": exported,
            "output_file": output_file,
            "success": True,
        }


def generate_sample_csv(file_path: str, num_records: int = 100) -> None:
    sample = []
    for i in range(num_records):
        sample.append(
            {
                "first_name": f"Test{i}",
                "last_name": f"User{i}",
                "email": f"test.user{i}@example.com",
                "phone": f"555-{i:04d}",
                "title": ["Manager", "Developer", "Analyst", "Director"][i % 4],
                "department": ["Sales", "Engineering", "Marketing", "Finance"][i % 4],
                "city": ["New York", "San Francisco", "Chicago", "Boston"][i % 4],
                "state": ["NY", "CA", "IL", "MA"][i % 4],
                "country": "USA",
            }
        )
    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(sample[0].keys()))
        writer.writeheader()
        writer.writerows(sample)
    print(f"Generated sample CSV with {num_records} records at {file_path}")


async def demonstrate_bulk_operations() -> None:
    config = SalesforceConfig()
    client = create_client_from_config(config.get_org_config(), config.get_rate_limit_config())

    async with client:
        processor = BulkDataProcessor(client)

        print("Salesforce Bulk Operations Demo")
        print("=" * 60)
        print()

        print("Example 1: Export Account Data")
        print("-" * 40)
        export_result = await processor.export_large_dataset(
            query="SELECT Id, Name, Industry, AnnualRevenue, NumberOfEmployees FROM Account",
            output_file="accounts_export.csv",
            batch_size=500,
        )
        print(
            f"Export completed: {export_result['exported']} records -> {export_result['output_file']}"
        )

        print("\nExample 2: Bulk Import")
        print("-" * 40)
        sample_csv = "sample_contacts.csv"
        generate_sample_csv(sample_csv, num_records=50)
        import_result = await processor.bulk_import_contacts(sample_csv)
        print(
            f"Import completed: {import_result['processed']} processed, "
            f"{import_result['failed']} failed "
            f"({import_result['success_rate']:.1f}% success)"
        )

        if os.path.exists(sample_csv):
            os.remove(sample_csv)
        if os.path.exists("accounts_export.csv"):
            os.remove("accounts_export.csv")


if __name__ == "__main__":
    required_vars = ["SALESFORCE_USERNAME", "SALESFORCE_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print("Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        raise SystemExit(1)

    asyncio.run(demonstrate_bulk_operations())
