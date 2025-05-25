# server/prompts/natural_language.py
import importlib.resources
import jinja2
from server.config import mcp
from server.logging_config import get_logger
from mcp.server.fastmcp.prompts import base

logger = get_logger("pg-mcp.prompts.natural_language")

# Set up Jinja2 template environment using importlib.resources
template_env = jinja2.Environment(
    loader=jinja2.FunctionLoader(lambda name: 
        importlib.resources.read_text('server.prompts.templates', name)
    )
)

def register_natural_language_prompts():
    """Register prompts with the MCP server."""
    logger.debug("Registering natural language to SQL prompts")

    @mcp.prompt()
    async def generate_sql(conn_id: str, nl_query: str):
        """
        Prompt to guide AI agents in converting natural language queries to SQL with PostgreSQL.

        Args:
            conn_id: The connection ID for the database
            nl_query: The natural language query to convert to SQL
        """
        # Get database information
        database_resource = f"pgmcp://{conn_id}/"
        database_response = await mcp.read_resource(database_resource)
        
        database_info = database_response[0].content if database_response else "{}"
        
        # Render the prompt template
        prompt_template = template_env.get_template("generate_sql.md.jinja2")
        prompt_text = prompt_template.render(
            database_info=database_info,
            nl_query=nl_query
        )
        
        return [base.UserMessage(prompt_text)]
    
    @mcp.prompt()
    async def validate_nl(conn_id: str, nl_query: str):
        """
        Prompt to determine if the user's query is answerable by the database
        and that a query can be generated. User input is evaluated on
        clarity/vagueness and also relevancy to the schema.
        
        Args:
            conn_id: The connection ID for the database
            nl_query: The natural language query to validate
        """
       # Get database information
        database_resource = f"pgmcp://{conn_id}/"
        database_response = await mcp.read_resource(database_resource)
        
        database_info = database_response[0].content if database_response else "{}"
        
        # Render the prompt template
        prompt_template = template_env.get_template("validate_nl.md.jinja2")
        prompt_text = prompt_template.render(
            database_info=database_info,
            nl_query=nl_query
        )
        
        return [base.UserMessage(prompt_text)]
    
    @mcp.prompt()
    async def justify_sql(conn_id: str, nl_query: str, sql_query: str):
        """
        Prompt to evaluate if a SQL query correctly answers a natural language question
        and provide an explanation of how the query works.
        
        Args:
            conn_id: The connection ID for the database
            nl_query: The original natural language query
            sql_query: The SQL query to evaluate and explain
        """
        # Get database information
        database_resource = f"pgmcp://{conn_id}/"
        database_response = await mcp.read_resource(database_resource)
        
        database_info = database_response[0].content if database_response else "{}"
        
        # Render the prompt template
        prompt_template = template_env.get_template("justify_sql.md.jinja2")
        prompt_text = prompt_template.render(
            database_info=database_info,
            nl_query=nl_query,
            sql_query=sql_query
        )
        
        return [base.UserMessage(prompt_text)]