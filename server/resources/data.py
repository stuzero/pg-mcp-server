# server/resources/data.py
from server.config import mcp
from server.logging_config import get_logger
from server.tools.query import execute_query

logger = get_logger("pg-mcp.resources.data")

def register_data_resources():
    """Register database data resources with the MCP server."""
    logger.debug("Registering data resources")
    
    @mcp.resource("pgmcp://{conn_id}/schemas/{schema}/tables/{table}/sample")
    async def sample_table_data(conn_id: str, schema: str, table: str):
        """Get a sample of data from a specific table."""
        # First, sanitize the schema and table names
        sanitize_query = "SELECT quote_ident($1) AS schema_ident, quote_ident($2) AS table_ident"
        identifiers = await execute_query(sanitize_query, conn_id, [schema, table])
        
        schema_ident = identifiers[0]['schema_ident']
        table_ident = identifiers[0]['table_ident']
        
        # Build the sample query with sanitized identifiers
        sample_query = f"SELECT * FROM {schema_ident}.{table_ident} LIMIT 10"
        return await execute_query(sample_query, conn_id)
    
    @mcp.resource("pgmcp://{conn_id}/schemas/{schema}/tables/{table}/rowcount")
    async def get_table_rowcount(conn_id: str, schema: str, table: str):
        """Get the approximate row count for a specific table."""
        # First, sanitize the schema and table names
        sanitize_query = "SELECT quote_ident($1) AS schema_ident, quote_ident($2) AS table_ident"
        identifiers = await execute_query(sanitize_query, conn_id, [schema, table])
        
        schema_ident = identifiers[0]['schema_ident']
        table_ident = identifiers[0]['table_ident']
        
        # Get approximate row count for the table (faster than COUNT(*))
        query = f"""
            SELECT 
                reltuples::bigint AS approximate_row_count
            FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE 
                pg_namespace.nspname = $1 
                AND pg_class.relname = $2
        """
        return await execute_query(query, conn_id, [schema, table])