# server/system/health.py
from server.config import mcp
from server.logging_config import get_logger
from starlette.responses import JSONResponse, Response
from starlette.requests import Request

logger = get_logger("pg-mcp.system.health")

def register_health():
    """Register the helper health-related endpoints with the MCP server."""
    logger.debug("Registering health endpoints")
    
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> Response:
        """
        Register a healthcheck endpoint for use in Docker and Kuberntes environments
            
        Returns:
            Dictionary containing the server status
        """
        return JSONResponse({"status": "ok"})
