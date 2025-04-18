# server/config.py
from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from server.database import Database
from mcp.server.fastmcp.utilities.logging import get_logger

logger = get_logger("pg-mcp.instance")

global_db = Database()
logger.info("Global database manager initialized")

@asynccontextmanager
async def app_lifespan(app: FastMCP) -> AsyncIterator[dict]:
    """Manage application lifecycle."""
    mcp.state = {"db": global_db}
    logger.info("Application startup - using global database manager")
    
    try:
        yield {"db": global_db}
    finally:
        # Don't close connections on individual session end
        pass

# Create the MCP instance
mcp = FastMCP(
    "pg-mcp-server", 
    debug=True, 
    lifespan=app_lifespan,
    dependencies=["asyncpg", "mcp"]
)