"""Custom exceptions for Salesforce MCP Server."""

from typing import Any


class SalesforceError(Exception):
    """Base exception for Salesforce-related errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(SalesforceError):
    """Raised when authentication fails."""

    def __init__(self, message: str, auth_type: str | None = None):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_FAILED",
            status_code=401
        )
        self.auth_type = auth_type


class AuthorizationError(SalesforceError):
    """Raised when user lacks permissions."""

    def __init__(self, message: str, required_permission: str | None = None):
        super().__init__(
            message=message,
            error_code="INSUFFICIENT_PRIVILEGES",
            status_code=403
        )
        self.required_permission = required_permission


class RateLimitError(SalesforceError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        limit: int | None = None,
        remaining: int | None = None
    ):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429
        )
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining


class ValidationError(SalesforceError):
    """Raised when data validation fails."""

    def __init__(
        self,
        message: str,
        field_errors: dict[str, list[str]] | None = None,
        available_fields: list[str] | None = None
    ):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400
        )
        self.field_errors = field_errors or {}
        self.available_fields = available_fields


class ObjectNotFoundError(SalesforceError):
    """Raised when a requested object doesn't exist."""

    def __init__(
        self,
        message: str,
        object_type: str | None = None,
        object_id: str | None = None
    ):
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=404
        )
        self.object_type = object_type
        self.object_id = object_id


class BulkOperationError(SalesforceError):
    """Raised when a bulk operation fails."""

    def __init__(
        self,
        message: str,
        job_id: str | None = None,
        failed_records: list[dict[str, Any]] | None = None
    ):
        super().__init__(
            message=message,
            error_code="BULK_OPERATION_FAILED",
            status_code=500
        )
        self.job_id = job_id
        self.failed_records = failed_records or []


class ApexExecutionError(SalesforceError):
    """Raised when Apex code execution fails."""

    def __init__(
        self,
        message: str,
        compile_error: str | None = None,
        runtime_error: str | None = None,
        line_number: int | None = None
    ):
        super().__init__(
            message=message,
            error_code="APEX_EXECUTION_ERROR",
            status_code=500
        )
        self.compile_error = compile_error
        self.runtime_error = runtime_error
        self.line_number = line_number


class ConnectionError(SalesforceError):
    """Raised when connection to Salesforce fails."""

    def __init__(
        self,
        message: str,
        endpoint: str | None = None,
        timeout: int | None = None
    ):
        super().__init__(
            message=message,
            error_code="CONNECTION_ERROR",
            status_code=503
        )
        self.endpoint = endpoint
        self.timeout = timeout
