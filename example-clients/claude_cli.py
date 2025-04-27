#!/usr/bin/env python
# example-clients/claude_cli.py
import asyncio
import dotenv
import os
import sys
import json
import anthropic
from mcp import ClientSession
from mcp.client.sse import sse_client
from tabulate import tabulate

# Load environment variables
dotenv.load_dotenv()
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
db_url = os.getenv('DATABASE_URL')
pg_mcp_url = os.getenv('PG_MCP_URL', 'http://localhost:8000/sse')

def clean_sql_query(sql_query):
    """
    Clean a SQL query by properly handling escaped quotes and trailing backslashes.
    
    Args:
        sql_query (str): The SQL query to clean
        
    Returns:
        str: Cleaned SQL query
    """
    # Handle escaped quotes - need to do this character by character to avoid issues with trailing backslashes
    import codecs
    
    # Use unicode_escape to properly handle all escape sequences
    result = codecs.decode(sql_query, 'unicode_escape')
    
    # Remove any extraneous whitespace or newlines
    result = result.strip()
    
    # Add trailing semicolon if missing
    if not result.endswith(';'):
        result += ';'
        
    return result

async def generate_sql_with_anthropic(user_query, conn_id, session):
    """
    Generate SQL using Claude with the server's generate_sql prompt.
    
    Args:
        user_query (str): The natural language query
        conn_id (str): The database connection ID
        session: The MCP client session
        
    Returns:
        dict: Dictionary with SQL and explanation
    """
    try:
        # Use the server's generate_sql prompt
        prompt_response = await session.get_prompt('generate_sql', {
            'conn_id': conn_id,
            'nl_query': user_query
        })
        
        # Process the prompt response
        if not hasattr(prompt_response, 'messages') or not prompt_response.messages:
            return {
                "success": False,
                "error": "Invalid prompt response from server"
            }
        
        # Convert MCP messages to format expected by Claude
        messages = []
        for msg in prompt_response.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content.text if hasattr(msg.content, 'text') else str(msg.content)
            })
        
        # Create the Claude client
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        
        # Get SQL from Claude
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1024,
            messages=messages
        )
        
        # Extract the SQL from the response
        response_text = response.content[0].text
        
        # Look for SQL in code blocks
        sql_query = None
        
        if "```sql" in response_text and "```" in response_text.split("```sql", 1)[1]:
            sql_start = response_text.find("```sql") + 6
            remaining_text = response_text[sql_start:]
            sql_end = remaining_text.find("```")
            
            if sql_end > 0:
                sql_query = remaining_text[:sql_end].strip()
        
        # If still no SQL query found, check if the whole response might be SQL
        if not sql_query and ("SELECT" in response_text or "WITH" in response_text):
            for keyword in ["WITH", "SELECT", "CREATE", "INSERT", "UPDATE", "DELETE"]:
                if keyword in response_text:
                    keyword_pos = response_text.find(keyword)
                    sql_query = response_text[keyword_pos:].strip()
                    for end_marker in ["\n\n", "```"]:
                        if end_marker in sql_query:
                            sql_query = sql_query[:sql_query.find(end_marker)].strip()
                    break
        
        if not sql_query:
            return {
                "success": False,
                "error": "Could not extract SQL from Claude's response",
                "response": response_text
            }
        
        return {
            "success": True,
            "sql": sql_query,
            "explanation": "SQL generated using Claude"
        }
            
    except Exception as e:
        print(f"Error calling Anthropic API: {e}")
        import traceback
        print(traceback.format_exc())
        return {
            "success": False,
            "error": f"Error: {str(e)}"
        }

async def main():
    # Check required environment variables
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)
    
    if not anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python claude_cli.py 'your natural language query'")
        sys.exit(1)
    
    user_query = sys.argv[1]
    print(f"Processing query: {user_query}")
    
    try:
        print(f"Connecting to MCP server at {pg_mcp_url}...")
        
        # Create the SSE client context manager
        async with sse_client(url=pg_mcp_url) as streams:
            print("SSE streams established, creating session...")
            
            # Create and initialize the MCP ClientSession
            async with ClientSession(*streams) as session:
                print("Session created, initializing...")
                
                # Initialize the connection
                await session.initialize()
                print("Connection initialized!")
                
                # Use the connect tool to register the connection
                print("Registering connection with server...")
                try:
                    connect_result = await session.call_tool(
                        "connect", 
                        {
                            "connection_string": db_url
                        }
                    )
                    
                    # Extract connection ID
                    if hasattr(connect_result, 'content') and connect_result.content:
                        content = connect_result.content[0]
                        if hasattr(content, 'text'):
                            result_data = json.loads(content.text)
                            conn_id = result_data.get('conn_id')
                            print(f"Connection registered with ID: {conn_id}")
                        else:
                            print("Error: Connection response missing text content")
                            sys.exit(1)
                    else:
                        print("Error: Connection response missing content")
                        sys.exit(1)
                except Exception as e:
                    print(f"Error registering connection: {e}")
                    sys.exit(1)
                
                # Generate SQL using Claude with schema context
                print("Generating SQL query with Claude...")
                response_data = await generate_sql_with_anthropic(user_query, conn_id, session)
                
                if not response_data["success"]:
                    print(f"Error: {response_data.get('error', 'Unknown error')}")
                    if "response" in response_data:
                        print(f"Claude response: {response_data['response']}")
                    sys.exit(1)
                
                # Extract SQL and explanation
                sql_query = response_data.get("sql", "")
                explanation = response_data.get("explanation", "")
                
                # Print the results
                if explanation:
                    print(f"\nExplanation:")
                    print(f"------------")
                    print(explanation)
                
                # Original query (as generated by Claude)
                print(f"\nGenerated SQL query:")
                print(f"------------------")
                print(sql_query)
                print(f"------------------\n")
                
                if not sql_query:
                    print("No SQL query was generated. Exiting.")
                    sys.exit(1)
                
                # Clean the SQL query before execution
                sql_query = clean_sql_query(sql_query)
                
                # Show the cleaned query
                print(f"Cleaned SQL query:")
                print(f"------------------")
                print(sql_query)
                print(f"------------------\n")
                
                # Execute the generated SQL query
                print("Executing SQL query...")
                try:
                    result = await session.call_tool(
                        "pg_query", 
                        {
                            "query": sql_query,
                            "conn_id": conn_id
                        }
                    )
                    
                    # Extract and format results
                    if hasattr(result, 'content') and result.content:
                        print("\nQuery Results:")
                        print("==============")
                        
                        # Extract multiple text items from content array
                        query_results = []
                        for item in result.content:
                            if hasattr(item, 'text') and item.text:
                                try:
                                    # Parse each text item as JSON
                                    row_data = json.loads(item.text)
                                    if isinstance(row_data, list):
                                        query_results.extend(row_data)
                                    else:
                                        query_results.append(row_data)
                                except json.JSONDecodeError:
                                    print(f"Warning: Could not parse result: {item.text}")
                        
                        if query_results:
                            # Pretty print the results
                            if isinstance(query_results, list) and len(query_results) > 0:
                                # Use tabulate to format the table
                                table = tabulate(
                                    query_results, 
                                    headers="keys",
                                    tablefmt="pretty",
                                    numalign="right",
                                    stralign="left"
                                )
                                print(table)
                                print(f"\nTotal rows: {len(query_results)}")
                            else:
                                print(json.dumps(query_results, indent=2))
                        else:
                            print("Query executed successfully but returned no results.")

                    else:
                        print("Query executed but returned no content.")
                except Exception as e:
                    print(f"Error executing SQL query: {type(e).__name__}: {e}")
                    print(f"Failed query was: {sql_query}")
                
                # Disconnect when done
                print("Disconnecting from database...")
                try:
                    await session.call_tool(
                        "disconnect", 
                        {
                            "conn_id": conn_id
                        }
                    )
                    print("Successfully disconnected.")
                except Exception as e:
                    print(f"Error during disconnect: {e}")
                
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())