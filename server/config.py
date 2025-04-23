# server/config.py
from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from server.database import Database
from server.logging_config import configure_logging, get_logger

# Initialize logging with our custom configuration
logger = get_logger("instance")

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