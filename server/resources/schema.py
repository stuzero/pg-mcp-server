# server/resources/schema.py
import os
import pathlib
from server.config import mcp
from mcp.server.fastmcp.utilities.logging import get_logger
from server.tools.query import execute_query

logger = get_logger("pg-mcp.resources.schemas")

# Define the SQL directory path
SQL_DIR = pathlib.Path(__file__).parent / "sql"

def load_sql_file(filename):
    """Load SQL from a file in the sql directory."""
    file_path = SQL_DIR / filename
    with open(file_path, 'r') as f:
        return f.read()

def register_schema_resources():
    """Register database schema resources with the MCP server."""
    logger.debug("Registering schema resources")

    @mcp.resource("pgmcp://{conn_id}/", mime_type="application/json")
    async def get_database(conn_id: str):
        """
        Get the complete database information including all schemas, tables, columns, and constraints.
        Returns a comprehensive JSON structure with the entire database structure.
        """
        query = load_sql_file("get_database.sql")
        result = await execute_query(query, conn_id)
        if result and len(result) > 0:
            return result[0]['db_structure']
        return {"schemas": []}
    
    @mcp.resource("pgmcp://{conn_id}/schemas", mime_type="application/json")
    async def list_schemas(conn_id: str):
        """Get all non-system schemas in the database."""
        query = load_sql_file("list_schemas.sql")
        result = await execute_query(query, conn_id)
        if result and len(result) > 0:
            return result[0]['schema_list']
        return {"schemas": []}
    
    @mcp.resource("pgmcp://{conn_id}/schemas/{schema}", mime_type="application/json")
    async def get_schema(conn_id: str, schema: str):
        """Get information about a particular  schemas in the database. Also provides extension information (if any)"""
        query = load_sql_file("get_schema.sql")
        result = await execute_query(query, conn_id, [schema])
        if result and len(result) > 0:
            return result[0]['schema_info']
        return {"schema": []}
    
    @mcp.resource("pgmcp://{conn_id}/schemas/{schema}/tables/{table}", mime_type="application/json")
    async def get_schema_table(conn_id: str, schema: str, table: str):
        """
        Get comprehensive information about a specific table in a schema.
        This returns detailed information including columns, constraints, indexes, and statistics.
        """
        query = load_sql_file("get_schema_table.sql")
        result = await execute_query(query, conn_id, [schema, table])
        if result and len(result) > 0:
            return result[0]['table_details']
        return {"table": {}}
    
    @mcp.resource("pgmcp://{conn_id}/schemas/{schema}/materialized_views/{view}", mime_type="application/json")
    async def get_schema_view(conn_id: str, schema: str, view: str):
        """
        Get comprehensive information about a specific materialized view in a schema.
        This returns detailed information including the view definition SQL, columns, 
        indexes, and statistics.
        """
        query = load_sql_file("get_schema_view.sql")
        result = await execute_query(query, conn_id, [schema, view])
        if result and len(result) > 0:
            return result[0]['view_details']
        return {"materialized_view": {}}