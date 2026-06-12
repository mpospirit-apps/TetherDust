# TetherDust MCP Server

Multi-agent AI database querying system via Model Context Protocol.

## Quick Start

### 1. Set Up Virtual Environment

```bash
cd tetherdust
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Configure Documentation

Create a `docs/` directory with your markdown documentation:

```
docs/
├── orders/
│   ├── tables.md      # Table schema documentation
│   └── queries.md     # Query examples
└── other-domain/
    └── ...
```

**Table Schema Format** (`tables.md`):
```markdown
## TableName
Description of the table.

| Column | Type | Description |
|--------|------|-------------|
| id | bigint NOT NULL | Primary key |
| status | varchar(20) | Status. Enum: ACTIVE, PENDING |
```

**Query Examples Format** (`queries.md`):
```markdown
### Query Title
Description of what the query does.

**Use cases:** order lookup, reporting
**Tables:** Order, Customer

​```sql
SELECT * FROM Order WHERE status = 'ACTIVE'
​```
```

### 3. Configure Database Connections

Add database connections through the Django admin console at `/console/databases/`. Each connection requires a name, engine type, host, port, database name, and credentials.

**Install database drivers as needed:**
```bash
pip install -e ".[postgresql]"  # PostgreSQL
pip install -e ".[mysql]"       # MySQL/MariaDB
pip install -e ".[mssql]"       # SQL Server
pip install -e ".[all-databases]"  # All drivers
```

### 4. Use with Codex CLI

From the project root (parent of `tetherdust/`):

```bash
codex
```

The MCP server will be available with 6 tools:
- `list_tables`, `get_table_schema`, `search_docs`, `get_query_examples`
- `list_databases`, `query_database`

## Security: Read-Only Database Users

**CRITICAL**: Always use read-only database users. Application-level validation is a secondary safeguard, not primary protection.

### PostgreSQL

```sql
CREATE ROLE tetherdust_readonly WITH LOGIN PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE mydb TO tetherdust_readonly;
GRANT USAGE ON SCHEMA public TO tetherdust_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tetherdust_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO tetherdust_readonly;
```

### MySQL / MariaDB

```sql
CREATE USER 'tetherdust_readonly'@'%' IDENTIFIED BY 'secure_password';
GRANT SELECT ON mydb.* TO 'tetherdust_readonly'@'%';
FLUSH PRIVILEGES;
```

### Microsoft SQL Server

```sql
CREATE LOGIN tetherdust_readonly WITH PASSWORD = 'secure_password';
USE mydb;
CREATE USER tetherdust_readonly FOR LOGIN tetherdust_readonly;
ALTER ROLE db_datareader ADD MEMBER tetherdust_readonly;
```

### Oracle

```sql
CREATE USER tetherdust_readonly IDENTIFIED BY secure_password;
GRANT CONNECT TO tetherdust_readonly;
GRANT SELECT ANY TABLE TO tetherdust_readonly;
-- Or more restrictive:
-- GRANT SELECT ON schema.table_name TO tetherdust_readonly;
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCS_PATH` | Path to documentation directory | `docs` |

## Running Standalone

```bash
cd tetherdust
python -m mcp_server.server
```

The server uses stdio transport for MCP communication.

## Project Structure

```
tetherdust/
├── mcp_server/
│   ├── server.py          # MCP entry point
│   ├── tools/
│   │   ├── docs.py        # list_tables, get_table_schema, search_docs
│   │   ├── examples.py    # get_query_examples
│   │   └── database.py    # list_databases, query_database
│   └── utils/
│       ├── db_service.py      # SQLAlchemy connection manager
│       └── markdown_parser.py # Documentation parser
└── pyproject.toml
```
