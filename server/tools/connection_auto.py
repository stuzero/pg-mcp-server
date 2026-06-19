# server/tools/connection_auto.py
# Extended connection tools with header-based credential support
from server.config import mcp
from mcp.server.fastmcp import Context
from server.logging_config import get_logger

logger = get_logger("pg-mcp.tools.connection_auto")

def register_connection_tools():
    """Register the database connection tools with the MCP server."""
    logger.debug("Registering database connection tools with auto-connect support")

    @mcp.tool()
    async def connect(connection_string: str = None, *, ctx: Context):
        """
        Register a database connection string and return its connection ID.

        If connection_string is not provided, attempts to build it from request headers:
        - X-Postgres-Host: Database host (e.g., poc.postgres.yellowmind.ai:3515)
        - X-Postgres-User: Database user (e.g., postgres)
        - X-Postgres-Password: Database password
        - X-Postgres-Database: Database name (e.g., smartadk)

        Args:
            connection_string: PostgreSQL connection string (optional if using headers)
            ctx: Request context (injected by the framework)

        Returns:
            Dictionary containing the connection ID
        """
        # Get database from context
        db = mcp.state["db"]

        # If no connection string provided, try to build from headers
        if not connection_string:
            # Try to get headers from the request context
            request = ctx.request_context if hasattr(ctx, 'request_context') else None
            headers = getattr(request, 'headers', {}) if request else {}

            # Build connection string from headers
            host = headers.get('x-postgres-host', '')
            user = headers.get('x-postgres-user', 'postgres')
            password = headers.get('x-postgres-password', '')
            database = headers.get('x-postgres-database', 'postgres')

            if not host:
                return {"error": "No connection_string provided and missing X-Postgres-Host header"}

            connection_string = f"postgresql://{user}:{password}@{host}/{database}"

        # Register the connection to get a connection ID
        conn_id = db.register_connection(connection_string)

        # Return the connection ID
        logger.info(f"Registered database connection with ID: {conn_id}")
        return {"conn_id": conn_id}

    @mcp.tool()
    async def disconnect(conn_id: str, *, ctx: Context):
        """
        Close a specific database connection and remove it from the pool.

        Args:
            conn_id: Connection ID to disconnect (required)
            ctx: Request context (injected by the framework)

        Returns:
            Dictionary indicating success status
        """
        # Get database from context
        db = mcp.state["db"]

        # Check if the connection exists
        if conn_id not in db._connection_map:
            logger.warning(f"Attempted to disconnect unknown connection ID: {conn_id}")
            return {"success": False, "error": "Unknown connection ID"}

        # Close the connection pool
        try:
            await db.close(conn_id)
            # Also remove from the connection mappings
            connection_string = db._connection_map.pop(conn_id, None)
            if connection_string in db._reverse_map:
                del db._reverse_map[connection_string]
            logger.info(f"Successfully disconnected database connection with ID: {conn_id}")
            return {"success": True}
        except Exception as e:
            logger.error(f"Error disconnecting connection {conn_id}: {e}")
            return {"success": False, "error": str(e)}
