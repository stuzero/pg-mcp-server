# server/tools/viz.py
import json
from datetime import date, datetime
from decimal import Decimal
from sqlglot import parse_one, exp
from server.config import mcp
from server.logging_config import get_logger

logger = get_logger("pg-mcp.tools.viz")

def pg_type_to_logical(pg_type) -> str:
    """Maps PostgreSQL type to logical type."""
    pg_type = pg_type.name.lower()
    if pg_type in {"int", "int4", "int8", "float4", "float8", "numeric", "decimal", "double precision"}:
        return "quantitative"
    elif pg_type in {"date", "timestamp", "timestamptz"}:
        return "temporal"
    else:
        return "nominal"
    
def default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

async def get_query_metadata(conn_id, sql_query):
    """
    Analyze a SQL query and produce metadata about the results.
    
    Args:
        conn_id: Database connection ID
        sql_query: The SQL query to analyze
    Returns:
        JSON metadata about the query results structure
    """
    # Get database from mcp state
    db = mcp.state["db"]
    
    # Sanitize SQL - remove trailing semicolon
    sql_query = sql_query.strip()
    if sql_query.endswith(';'):
        sql_query = sql_query[:-1]

    metadata = {
        "fields": [],
        "rowCount": 0,
        "groupBy": []
    }
    
    async with db.get_connection(conn_id) as conn:
        # --- Parse query AST ---
        try:
            ast = parse_one(sql_query)
            group_exprs = ast.args.get("group", [])
            if group_exprs:
                metadata["groupBy"] = [
                    g.name for g in group_exprs if isinstance(g, exp.Column)
                ]
        except Exception as e:
            logger.error(f"AST parse failed: {e}")
    
        # --- Get column names and types ---
        stmt = await conn.prepare(sql_query)
        column_attrs = stmt.get_attributes()
    
        for col in column_attrs:
            logical_type = pg_type_to_logical(col.type)
            field_meta = {"name": col.name, "type": logical_type}
    
            # Optional: try to get stats
            if logical_type == "nominal":
                query = f"SELECT COUNT(DISTINCT {col.name}) FROM ({sql_query}) AS subq"
                try:
                    result = await conn.fetchval(query)
                    field_meta["unique"] = result
                except Exception:
                    pass
    
            elif logical_type == "temporal":
                query = f"SELECT MIN({col.name}), MAX({col.name}) FROM ({sql_query}) AS subq"
                try:
                    result = await conn.fetchrow(query)
                    if result:
                        field_meta["range"] = [result[0], result[1]]
                except Exception:
                    pass
    
            metadata["fields"].append(field_meta)
    
        # --- Row count ---
        try:
            result = await conn.fetchval(f"SELECT COUNT(*) FROM ({sql_query}) AS subq")
            metadata["rowCount"] = result
        except Exception as e:
            logger.error(f"Row count failed: {e}")

    return json.dumps(metadata, indent=2, default=default_serializer)

def register_viz_tools():
    """Register visualization tools with the MCP server."""
    logger.debug("Registering vizualization tools")

    @mcp.tool()
    async def pg_metadata(conn_id: str, sql_query: str):
        """
        Analyzes a SQL query and produces visualization metadata.
        
        Args:
            conn_id: Connection ID previously obtained from the connect tool
            sql_query: The SQL query to analyze
            
        Returns:
            JSON metadata about the query results structure
        """
        # Call the function to get query metadata
        return await get_query_metadata(conn_id, sql_query)