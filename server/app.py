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
from starlette.middleware import Middleware
from starlette.requests import Request
import uvicorn

class PostgresConnectionMiddleware:
    """Middleware to extract PostgreSQL connection string from headers and store in MCP state.
    This middleware is ASGI-compliant and properly handles streaming responses like SSE.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Create a request object for header access
        request = Request(scope, receive=None)

        # Log ALL incoming requests for debugging
        logger.info("===== INCOMING REQUEST =====")
        logger.info("Method: %s", request.method)
        logger.info("URL: %s", str(request.url))
        logger.info("Path: %s", request.url.path)
        logger.info("Headers: %s", dict(request.headers))

        # Extract connection details from headers
        pg_host = request.headers.get("X-Postgres-Host") or request.headers.get("x-postgres-host")
        pg_user = request.headers.get("X-Postgres-User") or request.headers.get("x-postgres-user", "postgres")
        pg_password = request.headers.get("X-Postgres-Password") or request.headers.get("x-postgres-password")
        pg_database = request.headers.get("X-Postgres-Database") or request.headers.get("x-postgres-database", "postgres")
        pg_connection_string = request.headers.get("X-Postgres-Connection-String") or request.headers.get("x-postgres-connection-string")

        logger.info("PostgreSQL Headers - Host: %s, User: %s, Database: %s, Has Password: %s, Connection String: %s",
                    pg_host, pg_user, pg_database, bool(pg_password), bool(pg_connection_string))

        connection_string = None
        if pg_connection_string:
            connection_string = pg_connection_string
            logger.info("Using connection string from X-Postgres-Connection-String header")
        elif pg_host and pg_user and pg_password and pg_database:
            connection_string = f"postgresql://{pg_user}:{pg_password}@{pg_host}/{pg_database}"
            logger.info("Built connection string from individual headers")

        if connection_string:
            # Store in MCP state for access by tool functions
            if not hasattr(mcp, 'state') or mcp.state is None:
                mcp.state = {}
            mcp.state["postgres_connection_string"] = connection_string
            logger.info("✓ Stored PostgreSQL connection string in MCP state for host=%s", pg_host)
        else:
            logger.warning("✗ No PostgreSQL connection details found in headers")

        # Use a wrapper to log completion without interfering with streaming
        async def send_wrapper(message):
            if message.get("type") == "http.response.body" and not message.get("more_body"):
                logger.info("===== REQUEST COMPLETED =====\n")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            logger.error("Error in request processing: %s", e)
            raise

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
        lifespan=starlette_lifespan,
        middleware=[Middleware(PostgresConnectionMiddleware)]
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
