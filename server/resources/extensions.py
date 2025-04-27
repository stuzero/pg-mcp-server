# server/resources/extensions.py
import os
import yaml
from server.config import mcp
from server.logging_config import get_logger
from server.tools.query import execute_query

logger = get_logger("pg-mcp.resources.extensions")

def get_extension_yaml(extension_name):
    """Load and return extension context YAML if it exists."""
    extensions_dir = os.path.join(os.path.dirname(__file__), 'extensions')
    file_path = os.path.join(extensions_dir, f"{extension_name}.yaml")
    
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading extension YAML for {extension_name}: {e}")
    
    return None

def register_extension_resources():
    """Register database extension resources with the MCP server."""
    logger.debug("Registering extension resources")
    
    @mcp.resource("pgmcp://{conn_id}/schemas/{schema}/extensions")
    async def list_schema_extensions(conn_id: str, schema: str):
        """List all extensions installed in a specific schema."""
        query = """
            SELECT 
                e.extname AS name,
                e.extversion AS version,
                n.nspname AS schema,
                e.extrelocatable AS relocatable,
                obj_description(e.oid) AS description
            FROM 
                pg_extension e
            JOIN 
                pg_namespace n ON n.oid = e.extnamespace
            WHERE 
                n.nspname = $1
            ORDER BY 
                e.extname
        """
        extensions = await execute_query(query, conn_id, [schema])
        
        # Enhance with any available YAML context
        for ext in extensions:
            ext_name = ext.get('name')
            yaml_context = get_extension_yaml(ext_name)
            if yaml_context:
                ext['context_available'] = True
            else:
                ext['context_available'] = False
                
        return extensions
    
    @mcp.resource("pgmcp://{conn_id}/schemas/{schema}/extensions/{extension}")
    async def get_extension_details(conn_id: str, schema: str, extension: str):
        """Get detailed information about a specific extension in a schema."""
        # Return YAML context if available
        yaml_context = get_extension_yaml(extension)
        if yaml_context:
            return [yaml_context]
        
        # Return empty string if no YAML context
        return [""]