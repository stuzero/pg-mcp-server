# server/app.py
import os
from server.logging_config import configure_logging, get_logger, configure_uvicorn_logging

# Configure logging first thing to capture all subsequent log messages
log_level = os.environ.get("LOG_LEVEL", "DEBUG")
configure_logging(level=log_level)
logger = get_logger("app")

# Import MCP instance and other components after logging is configured
from server.config import mcp, global_db

# Import registration functions
from server.resources.schema import register_schema_resources
from server.resources.data import register_data_resources
from server.resources.extensions import register_extension_resources
from server.tools.connection import register_connection_tools
from server.tools.query import register_query_tools
from server.tools.viz import register_viz_tools
from server.prompts.natural_language import register_natural_language_prompts
from server.prompts.data_visualization import register_data_visualization_prompts

# Register tools and resources with the MCP server
logger.info("Registering resources and tools")
register_schema_resources()   # Schema-related resources (schemas, tables, columns)
register_extension_resources()
register_data_resources()     # Data-related resources (sample, rowcount, etc.)
register_connection_tools()   # Connection management tools
register_query_tools()
register_viz_tools()         # Visualization tools
register_natural_language_prompts()  # Natural language to SQL prompts
register_data_visualization_prompts() # Data visualization prompts


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
    app = Starlette(
        routes=[Mount('/', app=mcp.sse_app())],
        lifespan=starlette_lifespan
    )
    
    # Configure Uvicorn with our logging setup
    uvicorn_log_config = configure_uvicorn_logging(log_level)
    
    # Use our configured log level for Uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        log_level=log_level.lower(),
        log_config=uvicorn_log_config
    )