# server/tools/connection.py
# Connection tools with support for connection string from headers via middleware
from server.config import mcp
from mcp.server.fastmcp import Context
from server.logging_config import get_logger
import os

logger = get_logger("pg-mcp.tools.connection")

def register_connection_tools():
    """Register the database connection tools with the MCP server."""
    logger.debug("Registering database connection tools with header-based connection support")

    @mcp.tool()
    async def connect(connection_string: str = None, *, ctx: Context):
        """
        Register a database connection string and return its connection ID.

        The connection string can be provided:
        1. Directly as the connection_string parameter
        2. Via environment variables (for stdio transport):
           - POSTGRES_CONNECTION_STRING
           - Or POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DATABASE
        3. Via global state set by middleware (for SSE/HTTP transport)

        Args:
            connection_string: PostgreSQL connection string (optional)
            ctx: Request context (injected by the framework)

        Returns:
            Dictionary containing the connection ID or error
        """
        db = mcp.state["db"]

        # Try to get connection string from various sources
        if not connection_string:
            # Try global state (set by middleware for SSE/HTTP)
            connection_string = mcp.state.get("postgres_connection_string")

        if not connection_string:
            # Try environment variable (full connection string)
            connection_string = os.getenv('POSTGRES_CONNECTION_STRING')

        if not connection_string:
            # Try building from individual environment variables
            if all([
                os.getenv('POSTGRES_HOST'),
                os.getenv('POSTGRES_USER'),
                os.getenv('POSTGRES_PASSWORD'),
                os.getenv('POSTGRES_DATABASE'),
            ]):
                host = os.getenv('POSTGRES_HOST')
                user = os.getenv('POSTGRES_USER', 'postgres')
                password = os.getenv('POSTGRES_PASSWORD')
                database = os.getenv('POSTGRES_DATABASE', 'postgres')
                connection_string = "postgresql://{}:{}@{}/{}".format(user, password, host, database)

        if not connection_string:
            return {
                "error": "No connection_string provided. Configure via: "
                        "1. connector fixedParams, "
                        "2. POSTGRES_CONNECTION_STRING env var, or "
                        "3. POSTGRES_HOST/USER/PASSWORD/DATABASE env vars"
            }

        # Ensure connection string has the correct format
        if not connection_string.startswith("postgresql://"):
            connection_string = f"postgresql://{connection_string}"

        # Register the connection to get a connection ID
        conn_id = db.register_connection(connection_string)

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
