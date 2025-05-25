# server/prompts/data_visualization.py
import importlib.resources
import jinja2
from server.config import mcp
from server.logging_config import get_logger
from mcp.server.fastmcp.prompts import base
from server.tools.viz import get_query_metadata

logger = get_logger("pg-mcp.prompts.data_visualization")

# Set up Jinja2 template environment using importlib.resources
template_env = jinja2.Environment(
    loader=jinja2.FunctionLoader(lambda name: 
        importlib.resources.read_text('server.prompts.templates', name)
    )
)

def register_data_visualization_prompts():
    """Register data visualization prompts with the MCP server."""
    logger.debug("Registering data visualization prompts")

    @mcp.prompt()
    async def generate_vega(conn_id: str, nl_query: str, sql_query: str):
        """
        Prompt to guide AI agents in generating appropriate Vega-Lite visualizations
        based on SQL query results, metadata, and database context.

        Args:
            conn_id: The connection ID for the database
            nl_query: The original natural language query
            sql_query: The SQL query to visualize
            
        Returns:
            A prompt message that will guide the AI in generating a Vega-Lite specification
        """
        # Generate query metadata directly using the updated function
        logger.debug(f"Generating query metadata")
        query_metadata = await get_query_metadata(conn_id, sql_query)
        logger.debug(f"Query metadata generated successfully")
        
        # Get database information for context
        database_resource = f"pgmcp://{conn_id}/"
        database_response = await mcp.read_resource(database_resource)
        
        database_info = database_response[0].content if database_response else "{}"
        
        # Render the prompt template
        prompt_template = template_env.get_template("generate_vega.md.jinja2")
        prompt_text = prompt_template.render(
            database_info=database_info,
            nl_query=nl_query,
            sql_query=sql_query,
            query_metadata=query_metadata
        )
        
        return [base.UserMessage(prompt_text)]