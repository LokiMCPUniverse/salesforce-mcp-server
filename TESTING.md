# Testing Guide for Salesforce MCP Server

## Quick Start

### Run All Tests
```bash
pytest tests/ -v
```

### Run with Coverage
```bash
pytest tests/ --cov=salesforce_mcp --cov-report=html
```

### Run Linter
```bash
ruff check src/ tests/
```

### Run All CI Checks
```bash
# Install dependencies
pip install -e .
pip install pytest pytest-asyncio pytest-cov pytest-mock ruff

# Run checks
ruff check src/ tests/
pytest tests/ -v --cov=salesforce_mcp
```

## Test Categories

### Authentication Tests (13 tests)
- Username/Password authentication
- OAuth 2.0 Web Server Flow
- JWT Bearer Token Flow
- Token validation and refresh

### Client Tests (16 tests)
- SOQL query execution
- Record CRUD operations
- Bulk API operations
- Apex code execution
- Error handling (400, 404, 429, 401)
- Rate limiting
- CSV conversion for bulk API

### Server Tests (13 tests)
- Tool listing
- Tool execution for all operations
- Multi-org support
- Audit logging
- Error propagation

## Current Test Status

✅ **42 tests passing (100%)**
✅ **All linting checks pass**
✅ **No security vulnerabilities**

## GitHub Actions CI

The GitHub Actions workflow automatically runs on:
- Push to main or develop branches
- Pull requests to main branch

It tests on Python 3.8, 3.9, 3.10, and 3.11.

### Workflow Steps
1. Install dependencies
2. Run ruff linter (fails on issues)
3. Run pytest (fails on test failures)
4. Generate coverage report
5. Build package
6. Validate package

## Manual Testing

To test the server manually:

```python
from salesforce_mcp import SalesforceMCPServer
from salesforce_mcp.config import SalesforceConfig

# Create configuration (will use environment variables)
config = SalesforceConfig()

# Create and instantiate server
server = SalesforceMCPServer(config)
print(f"Server created: {server.server.name}")
```

## Environment Setup for Testing

Create a `.env` file for local testing:

```env
SALESFORCE_USERNAME=test@example.com
SALESFORCE_PASSWORD=password123
SALESFORCE_SECURITY_TOKEN=token123
SALESFORCE_DOMAIN=test
```

Note: The tests use mocked authentication, so no real Salesforce credentials are needed.
