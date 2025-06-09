# Salesforce MCP Server

A highly customizable Model Context Protocol (MCP) server for integrating Salesforce APIs with GenAI applications.

## Features

- **Comprehensive Salesforce API Coverage**:
  - SOQL queries for data retrieval
  - Record CRUD operations (Create, Read, Update, Delete)
  - Metadata API access
  - Bulk API operations
  - Apex REST endpoint calls
  - Reports and dashboards access
  
- **Flexible Authentication**:
  - OAuth 2.0 Web Server Flow
  - OAuth 2.0 JWT Bearer Flow
  - Username-Password Flow
  - Connected App support

- **Enterprise-Ready**:
  - Multi-org support
  - Rate limiting and retry logic
  - Comprehensive error handling
  - Audit logging
  - Field-level security respect

## Installation

```bash
pip install salesforce-mcp-server
```

Or install from source:

```bash
git clone https://github.com/asklokesh/salesforce-mcp-server.git
cd salesforce-mcp-server
pip install -e .
```

## Configuration

Create a `.env` file or set environment variables:

```env
# Salesforce Credentials
SALESFORCE_USERNAME=your_username@company.com
SALESFORCE_PASSWORD=your_password
SALESFORCE_SECURITY_TOKEN=your_security_token
SALESFORCE_DOMAIN=login  # or test, or your custom domain

# OR use OAuth
SALESFORCE_CLIENT_ID=your_connected_app_client_id
SALESFORCE_CLIENT_SECRET=your_connected_app_client_secret
SALESFORCE_REDIRECT_URI=http://localhost:8080/callback

# Optional Settings
SALESFORCE_API_VERSION=59.0
SALESFORCE_SANDBOX=false
SALESFORCE_MAX_RETRIES=3
SALESFORCE_TIMEOUT=30
```

## Quick Start

### Basic Usage

```python
from salesforce_mcp import SalesforceMCPServer

# Initialize the server
server = SalesforceMCPServer()

# Start the server
server.start()
```

### Claude Desktop Configuration

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "salesforce": {
      "command": "python",
      "args": ["-m", "salesforce_mcp.server"],
      "env": {
        "SALESFORCE_USERNAME": "your_username@company.com",
        "SALESFORCE_PASSWORD": "your_password",
        "SALESFORCE_SECURITY_TOKEN": "your_security_token"
      }
    }
  }
}
```

## Available Tools

### 1. Query Records
Execute SOQL queries to retrieve data:
```python
{
  "tool": "salesforce_query",
  "arguments": {
    "query": "SELECT Id, Name, Email FROM Contact WHERE LastModifiedDate = TODAY",
    "include_deleted": false
  }
}
```

### 2. Get Record
Retrieve a specific record by ID:
```python
{
  "tool": "salesforce_get_record",
  "arguments": {
    "object_type": "Account",
    "record_id": "001XX000003DHPh",
    "fields": ["Name", "Industry", "AnnualRevenue"]
  }
}
```

### 3. Create Record
Create new records:
```python
{
  "tool": "salesforce_create_record",
  "arguments": {
    "object_type": "Contact",
    "data": {
      "FirstName": "John",
      "LastName": "Doe",
      "Email": "john.doe@example.com",
      "AccountId": "001XX000003DHPh"
    }
  }
}
```

### 4. Update Record
Update existing records:
```python
{
  "tool": "salesforce_update_record",
  "arguments": {
    "object_type": "Contact",
    "record_id": "003XX000004TMM2",
    "data": {
      "Title": "Senior Developer",
      "Department": "Engineering"
    }
  }
}
```

### 5. Delete Record
Delete records:
```python
{
  "tool": "salesforce_delete_record",
  "arguments": {
    "object_type": "Contact",
    "record_id": "003XX000004TMM2"
  }
}
```

### 6. Describe Object
Get metadata about Salesforce objects:
```python
{
  "tool": "salesforce_describe_object",
  "arguments": {
    "object_type": "Account"
  }
}
```

### 7. Bulk Operations
Handle large data volumes:
```python
{
  "tool": "salesforce_bulk_create",
  "arguments": {
    "object_type": "Contact",
    "records": [
      {"FirstName": "Jane", "LastName": "Smith", "Email": "jane@example.com"},
      {"FirstName": "Bob", "LastName": "Johnson", "Email": "bob@example.com"}
    ],
    "batch_size": 200
  }
}
```

### 8. Execute Apex
Run Apex code:
```python
{
  "tool": "salesforce_execute_apex",
  "arguments": {
    "apex_body": "System.debug('Hello from Apex!');"
  }
}
```

## Advanced Configuration

### Multi-Org Support

```python
from salesforce_mcp import SalesforceMCPServer, OrgConfig

# Configure multiple orgs
orgs = {
    "production": OrgConfig(
        username="prod@company.com",
        password="prod_password",
        security_token="prod_token",
        domain="login"
    ),
    "sandbox": OrgConfig(
        username="sandbox@company.com.sandbox",
        password="sandbox_password",
        security_token="sandbox_token",
        domain="test"
    )
}

server = SalesforceMCPServer(orgs=orgs, default_org="production")
```

### Custom Authentication

```python
from salesforce_mcp import SalesforceMCPServer, JWTAuth

# JWT Bearer Flow
jwt_auth = JWTAuth(
    client_id="your_client_id",
    username="your_username",
    private_key_file="path/to/private_key.pem",
    sandbox=False
)

server = SalesforceMCPServer(auth=jwt_auth)
```

### Rate Limiting

```python
from salesforce_mcp import SalesforceMCPServer, RateLimitConfig

rate_limit = RateLimitConfig(
    requests_per_second=10,
    burst_size=20,
    wait_on_limit=True
)

server = SalesforceMCPServer(rate_limit=rate_limit)
```

## Integration Examples

See the `examples/` directory for complete integration examples:

- `basic_usage.py` - Simple queries and CRUD operations
- `bulk_operations.py` - Handling large data volumes
- `genai_integration.py` - Integration with GenAI APIs
- `multi_org.py` - Managing multiple Salesforce orgs
- `oauth_flow.py` - OAuth authentication setup

## Error Handling

The server provides detailed error information:

```python
try:
    result = server.execute_tool("salesforce_query", {
        "query": "SELECT InvalidField FROM Account"
    })
except SalesforceError as e:
    print(f"Salesforce error: {e.error_code} - {e.message}")
    print(f"Fields available: {e.available_fields}")
```

## Security Best Practices

1. **Never commit credentials** - Use environment variables or secure vaults
2. **Use OAuth when possible** - More secure than username/password
3. **Implement field-level security** - Respect Salesforce permissions
4. **Enable audit logging** - Track all API operations
5. **Use IP restrictions** - Limit access to known IP ranges

## Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests.

## License

MIT License - see LICENSE file for details