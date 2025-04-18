# server/app.py
from mcp.server.fastmcp.utilities.logging import configure_logging, get_logger
import logging
import sys

# Configure logging
configure_logging(level="DEBUG")
logger = get_logger("pg-mcp")

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(handler)

# Import mcp instance
from server.config import mcp, global_db

# Import registration functions
from server.resources.schema import register_schema_resources
from server.resources.data import register_data_resources
from server.resources.extensions import register_extension_resources
from server.tools.connection import register_connection_tools
from server.tools.query import register_query_tools
from server.prompts.nl_to_sql import register_nl_prompts

# Register tools and resources with the MCP server
register_schema_resources()   # Schema-related resources (schemas, tables, columns)
register_extension_resources()
register_data_resources()     # Data-related resources (sample, rowcount, etc.)
register_connection_tools()  # Connection management tools
register_query_tools()
register_nl_prompts()  # Register prompt

from contextlib import asynccontextmanager
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn

@asynccontextmanager
async def starlette_lifespan(app):
    logger.info("Starlette application starting up")
    yield
    logger.info("Starlette application shutting down, closing all database connections")
    await global_db.close()

if __name__ == "__main__":
    logger.info("Starting MCP server with SSE transport")
    app = Starlette(routes=[Mount('/', app=mcp.sse_app())])
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")