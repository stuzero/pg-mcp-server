# server/prompts/nl_to_sql.py
from server.config import mcp
from mcp.server.fastmcp.utilities.logging import get_logger
from mcp.server.fastmcp.prompts import base

logger = get_logger("pg-mcp.prompts.nl_to_sql")

def register_nl_prompts():
    """Register prompts with the MCP server."""
    logger.debug("Registering prompts")

    @mcp.prompt()
    def nl_to_sql_prompt(query: str, schema_json: str = None):
        """
        Prompt to guide AI agents in converting natural language queries to SQL with PostgreSQL.

        Args:
            query: The natural language query to convert to SQL
            schema_json: JSON representation of the database schema (optional, can be fetched by server)
        """
        schema_section = f"""
# Database Schema
```json
{schema_json}
```
    """ if schema_json else ""

        return [
            base.UserMessage(f"""
You are an expert PostgreSQL database query assistant. Your task is to:

Analyze the database schema information provided
Convert natural language questions into optimized PostgreSQL SQL queries
Use appropriate JOINs, WHERE clauses, and aggregations based on the schema

    {schema_section}
Response Format
Your response must contain ONLY the PostgreSQL SQL query inside sql code blocks.
Do not include any explanations, analysis, or comments outside of the SQL code block.
Keep your query concise and focused on answering the specific question.
Example response format:
```sql
SELECT column1, column2
FROM table1
JOIN table2 ON table1.id = table2.id
WHERE condition = true;
```
Query Writing Guidelines

Start by examining the database schema to understand table relationships
Use explicit column names rather than SELECT *
Use appropriate JOIN types (INNER, LEFT, RIGHT) based on the relationship
For filtering, use appropriate operators and functions (=, LIKE, IN, etc.)
Use CTEs (WITH clauses) for complex queries to improve readability
Include LIMIT clauses for queries that might return large result sets
Prefer schema-qualified table names (schema_name.table_name)
For performance, consider using indexed columns in WHERE clauses
End all SQL queries with a semicolon
Make sure your SQL query fits within a single response (don't create excessively long queries)

PostgreSQL-Specific Features

Use jsonb_* functions for JSON data handling
Consider using LATERAL joins for row-based subqueries
Use array functions (unnest, array_agg) for array operations
Use window functions (OVER, RANK, etc.) for analytic queries
For full-text search, utilize tsvector, tsquery, and indexing

Natural Language Query
    "{query}"
    """)
    ]