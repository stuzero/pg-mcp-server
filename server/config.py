# server/config.py
import os
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
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

transport_security = TransportSecuritySettings()

PG_MCP_SERVER_ALLOWED_HOSTS = os.getenv("PG_MCP_SERVER_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*")
allowed_hosts = [host for host in PG_MCP_SERVER_ALLOWED_HOSTS.split(",") if not host.isspace() and len(host) != 0]
transport_security.allowed_hosts.extend(allowed_hosts)

PG_MCP_SERVER_ALLOWED_ORIGINS = os.getenv("PG_MCP_SERVER_ALLOWED_ORIGINS", "http://localhost:*,http://127.0.0.1:*")
allowed_origins = [origin for origin in PG_MCP_SERVER_ALLOWED_ORIGINS.split(",") if not origin.isspace() and len(origin) != 0]
transport_security.allowed_origins.extend(allowed_origins)

logger.info("Registering following allowed hosts: %s", transport_security.allowed_hosts)
logger.info("Registering following allowed origins: %s", transport_security.allowed_origins)

# Create the MCP instance
mcp = FastMCP(
    "pg-mcp-server", 
    debug=True, 
    lifespan=app_lifespan,
    dependencies=["asyncpg", "mcp"],
    transport_security=transport_security
)
