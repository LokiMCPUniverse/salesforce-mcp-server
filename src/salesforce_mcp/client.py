"""Salesforce API client implementation."""

import json
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import httpx
from urllib.parse import quote

from .auth import AuthBase, UsernamePasswordAuth
from .config import OrgConfig, RateLimitConfig
from .exceptions import (
    SalesforceError,
    ValidationError,
    ObjectNotFoundError,
    RateLimitError,
    BulkOperationError,
    ApexExecutionError
)


class RateLimiter:
    """Simple rate limiter implementation."""
    
    def __init__(self, config: RateLimitConfig):
        self.requests_per_second = config.requests_per_second
        self.burst_size = config.burst_size
        self.wait_on_limit = config.wait_on_limit
        self.tokens = float(self.burst_size)
        self.last_update = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a token for making a request."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst_size,
                self.tokens + elapsed * self.requests_per_second
            )
            self.last_update = now
            
            if self.tokens < 1:
                if self.wait_on_limit:
                    wait_time = (1 - self.tokens) / self.requests_per_second
                    await asyncio.sleep(wait_time)
                    self.tokens = 1
                else:
                    raise RateLimitError(
                        "Rate limit exceeded",
                        retry_after=int((1 - self.tokens) / self.requests_per_second)
                    )
            
            self.tokens -= 1


class SalesforceClient:
    """Client for interacting with Salesforce APIs."""
    
    def __init__(
        self,
        auth: AuthBase,
        api_version: str = "59.0",
        timeout: int = 30,
        max_retries: int = 3,
        rate_limiter: Optional[RateLimiter] = None
    ):
        self.auth = auth
        self.api_version = api_version
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limiter = rate_limiter
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Make an authenticated request to Salesforce."""
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        
        if not self.auth.instance_url:
            await self.auth.authenticate()
        
        url = f"{self.auth.instance_url}{endpoint}"
        headers = await self.auth.get_headers()
        
        if not self._client:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await self._client.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )
            
            if response.status_code == 401 and retry_count < self.max_retries:
                # Token might be expired, try to re-authenticate
                await self.auth.authenticate()
                return await self._make_request(
                    method, endpoint, data, params, retry_count + 1
                )
            
            response.raise_for_status()
            
            if response.content:
                return response.json()
            return {}
            
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
    
    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP errors from Salesforce."""
        try:
            error_data = error.response.json()
        except:
            error_data = [{"message": str(error), "errorCode": "UNKNOWN_ERROR"}]
        
        if isinstance(error_data, list) and error_data:
            error_info = error_data[0]
        else:
            error_info = error_data
        
        message = error_info.get("message", str(error))
        error_code = error_info.get("errorCode", "UNKNOWN_ERROR")
        
        if error.response.status_code == 400:
            raise ValidationError(message, field_errors=error_info.get("fields", {}))
        elif error.response.status_code == 404:
            raise ObjectNotFoundError(message)
        elif error.response.status_code == 429:
            raise RateLimitError(
                message,
                retry_after=int(error.response.headers.get("Retry-After", 60))
            )
        else:
            raise SalesforceError(
                message,
                error_code=error_code,
                status_code=error.response.status_code
            )
    
    async def query(
        self,
        soql: str,
        include_deleted: bool = False
    ) -> Dict[str, Any]:
        """Execute a SOQL query."""
        endpoint = f"/services/data/v{self.api_version}/query"
        if include_deleted:
            endpoint = f"/services/data/v{self.api_version}/queryAll"
        
        params = {"q": soql}
        return await self._make_request("GET", endpoint, params=params)
    
    async def get_record(
        self,
        object_type: str,
        record_id: str,
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Retrieve a single record."""
        endpoint = f"/services/data/v{self.api_version}/sobjects/{object_type}/{record_id}"
        
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        
        return await self._make_request("GET", endpoint, params=params)
    
    async def create_record(
        self,
        object_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new record."""
        endpoint = f"/services/data/v{self.api_version}/sobjects/{object_type}"
        return await self._make_request("POST", endpoint, data=data)
    
    async def update_record(
        self,
        object_type: str,
        record_id: str,
        data: Dict[str, Any]
    ) -> None:
        """Update an existing record."""
        endpoint = f"/services/data/v{self.api_version}/sobjects/{object_type}/{record_id}"
        await self._make_request("PATCH", endpoint, data=data)
    
    async def delete_record(
        self,
        object_type: str,
        record_id: str
    ) -> None:
        """Delete a record."""
        endpoint = f"/services/data/v{self.api_version}/sobjects/{object_type}/{record_id}"
        await self._make_request("DELETE", endpoint)
    
    async def describe_object(
        self,
        object_type: str
    ) -> Dict[str, Any]:
        """Get metadata about an object."""
        endpoint = f"/services/data/v{self.api_version}/sobjects/{object_type}/describe"
        return await self._make_request("GET", endpoint)
    
    async def describe_global(self) -> Dict[str, Any]:
        """Get metadata about all objects."""
        endpoint = f"/services/data/v{self.api_version}/sobjects"
        return await self._make_request("GET", endpoint)
    
    async def bulk_create(
        self,
        object_type: str,
        records: List[Dict[str, Any]],
        batch_size: int = 200
    ) -> Dict[str, Any]:
        """Create multiple records using Bulk API 2.0."""
        # Create job
        job_endpoint = f"/services/data/v{self.api_version}/jobs/ingest"
        job_data = {
            "object": object_type,
            "operation": "insert"
        }
        job = await self._make_request("POST", job_endpoint, data=job_data)
        job_id = job["id"]
        
        try:
            # Upload data in batches
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                csv_data = self._records_to_csv(batch)
                
                batch_endpoint = f"/services/data/v{self.api_version}/jobs/ingest/{job_id}/batches"
                headers = await self.auth.get_headers()
                headers["Content-Type"] = "text/csv"
                
                await self._client.put(
                    f"{self.auth.instance_url}{batch_endpoint}",
                    headers=headers,
                    content=csv_data
                )
            
            # Start job processing
            job_endpoint = f"/services/data/v{self.api_version}/jobs/ingest/{job_id}"
            await self._make_request(
                "PATCH",
                job_endpoint,
                data={"state": "UploadComplete"}
            )
            
            # Wait for completion
            while True:
                job_status = await self._make_request("GET", job_endpoint)
                if job_status["state"] in ["JobComplete", "Failed", "Aborted"]:
                    break
                await asyncio.sleep(2)
            
            if job_status["state"] != "JobComplete":
                raise BulkOperationError(
                    f"Bulk job failed: {job_status.get('stateMessage', 'Unknown error')}",
                    job_id=job_id
                )
            
            return job_status
            
        except Exception as e:
            # Abort job on error
            try:
                await self._make_request(
                    "PATCH",
                    f"/services/data/v{self.api_version}/jobs/ingest/{job_id}",
                    data={"state": "Aborted"}
                )
            except:
                pass
            raise
    
    def _records_to_csv(self, records: List[Dict[str, Any]]) -> str:
        """Convert records to CSV format for bulk API."""
        if not records:
            return ""
        
        # Get all field names
        fields = set()
        for record in records:
            fields.update(record.keys())
        fields = sorted(fields)
        
        # Build CSV
        lines = [",".join(fields)]
        for record in records:
            values = []
            for field in fields:
                value = record.get(field, "")
                if value is None:
                    value = ""
                elif isinstance(value, (dict, list)):
                    value = json.dumps(value)
                values.append(str(value))
            lines.append(",".join(values))
        
        return "\n".join(lines)
    
    async def execute_apex(self, apex_body: str) -> Dict[str, Any]:
        """Execute anonymous Apex code."""
        endpoint = f"/services/data/v{self.api_version}/tooling/executeAnonymous"
        params = {"anonymousBody": apex_body}
        
        result = await self._make_request("GET", endpoint, params=params)
        
        if not result.get("success", False):
            compile_problem = result.get("compileProblem")
            exception_message = result.get("exceptionMessage")
            line = result.get("line")
            
            raise ApexExecutionError(
                "Apex execution failed",
                compile_error=compile_problem,
                runtime_error=exception_message,
                line_number=line
            )
        
        return result
    
    async def get_reports(self) -> Dict[str, Any]:
        """Get list of available reports."""
        endpoint = f"/services/data/v{self.api_version}/analytics/reports"
        return await self._make_request("GET", endpoint)
    
    async def run_report(
        self,
        report_id: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run a report and get results."""
        endpoint = f"/services/data/v{self.api_version}/analytics/reports/{report_id}"
        data = {"reportMetadata": filters} if filters else None
        return await self._make_request("POST", endpoint, data=data)


def create_client_from_config(org_config: OrgConfig, rate_limit_config: Optional[RateLimitConfig] = None) -> SalesforceClient:
    """Create a Salesforce client from configuration."""
    # Determine auth method
    if org_config.username and org_config.password:
        auth = UsernamePasswordAuth(
            username=org_config.username,
            password=org_config.password.get_secret_value() if org_config.password else "",
            security_token=org_config.security_token.get_secret_value() if org_config.security_token else "",
            domain=org_config.domain,
            client_id=org_config.client_id,
            client_secret=org_config.client_secret.get_secret_value() if org_config.client_secret else None
        )
    else:
        raise ValueError("Authentication configuration required")
    
    # Create rate limiter if configured
    rate_limiter = None
    if rate_limit_config:
        rate_limiter = RateLimiter(rate_limit_config)
    
    return SalesforceClient(
        auth=auth,
        api_version=org_config.api_version,
        timeout=org_config.timeout,
        max_retries=org_config.max_retries,
        rate_limiter=rate_limiter
    )