# get_schema.py
import asyncio
import httpx
import json
import sys
from mcp import ClientSession
from mcp.client.sse import sse_client

async def run(connection_string: str | None):
    """Download a comprhensive database schema from the MCP server."""
    # Assuming your server is running on localhost:8000
    server_url = "http://localhost:8000/sse"  
    
    try:
        print(f"Connecting to MCP server at {server_url}...")
        if connection_string:
            # Clean and sanitize the connection string
            clean_connection = connection_string.strip()
            # Only show a small part of the connection string for security
            masked_conn_string = clean_connection[:10] + "..." if len(clean_connection) > 10 else clean_connection
            print(f"Using database connection: {masked_conn_string}")
        
        # Create the SSE client context manager
        async with sse_client(url=server_url) as streams:
            print("SSE streams established, creating session...")
            
            # Create and initialize the MCP ClientSession
            async with ClientSession(*streams) as session:
                print("Session created, initializing...")
                # Initialize the connection
                await session.initialize()
                print("Connection initialized!")

                tools_response = await session.list_tools()
                tools = tools_response.tools

                if connection_string:
                    # Check if required tools are available
                    has_connect = any(tool.name == 'connect' for tool in tools)
                    
                    if not has_connect:
                        print("\nERROR: 'connect' tool is not available on the server")
                        return
                        
                    try:
                        # Use the cleaned connection string
                        clean_connection = connection_string.strip()
                        
                        # First, register the connection to get a conn_id
                        print("\nRegistering connection with 'connect' tool...")
                        connect_result = await session.call_tool(
                            "connect", 
                            {
                                "connection_string": clean_connection
                            }
                        )
                        
                        # Extract conn_id from the response
                        conn_id = None
                        if hasattr(connect_result, 'content') and connect_result.content:
                            content = connect_result.content[0]
                            if hasattr(content, 'text'):
                                try:
                                    result_data = json.loads(content.text)
                                    conn_id = result_data.get('conn_id')
                                    print(f"Successfully connected with connection ID: {conn_id}")
                                except json.JSONDecodeError:
                                    print(f"Error parsing connect result: {content.text[:100]}")
                        
                        if not conn_id:
                            print("Failed to get connection ID from connect tool")
                            return
                        
                        # Connect to the new comprehensive schema resource
                        print("\nConnecting to the comprehensive schema resource...")
                        schema_resource = f"pgmcp://{conn_id}/"
                        schema_response = await session.read_resource(schema_resource)
                        
                        # Process schema response
                        response_content = None
                        if hasattr(schema_response, 'content') and schema_response.content:
                            response_content = schema_response.content
                        elif hasattr(schema_response, 'contents') and schema_response.contents:
                            response_content = schema_response.contents
                        
                        if response_content:
                            content_item = response_content[0]
                            if hasattr(content_item, 'text'):
                                try:
                                    schema_data = json.loads(content_item.text)
                                    schemas = schema_data.get('schemas', [])
                                    
                                    print(f"Successfully retrieved schema for {len(schemas)} schemas")

                                    # Save the schema to a file for inspection
                                    output_file = f"{conn_id}.json"
                                    with open(output_file, 'w') as f:
                                        json.dump(schema_data, f, indent=2)
                                    print("\nComprehensive Database Schema saved to file")
                                    
                                except json.JSONDecodeError:
                                    print(f"Error parsing schema response: {content_item.text[:100]}")
                            else:
                                print("Schema response content has no text attribute")
                        else:
                            print("Schema response has no content")
                        
                        # Test disconnect tool if available
                        has_disconnect = any(tool.name == 'disconnect' for tool in tools)
                        if has_disconnect and conn_id:
                            print("\nDisconnecting...")
                            disconnect_result = await session.call_tool(
                                "disconnect", 
                                {
                                    "conn_id": conn_id
                                }
                            )
                            
                            if hasattr(disconnect_result, 'content') and disconnect_result.content:
                                content = disconnect_result.content[0]
                                if hasattr(content, 'text'):
                                    try:
                                        result_data = json.loads(content.text)
                                        success = result_data.get('success', False)
                                        if success:
                                            print(f"Successfully disconnected connection {conn_id}")
                                        else:
                                            error = result_data.get('error', 'Unknown error')
                                            print(f"Failed to disconnect: {error}")
                                    except json.JSONDecodeError:
                                        print(f"Error parsing disconnect result: {content.text[:100]}")
                            else:
                                print("Disconnect call completed but no result returned")
                        
                    except Exception as e:
                        print(f"Error during connection tests: {e}")
                else:
                    print("\nNo connection string provided, skipping database tests")

    except httpx.HTTPStatusError as e:
        print(f"HTTP Error: {e}")
        print(f"Status code: {e.response.status_code}")
        print(f"Response body: {e.response.text}")
    except httpx.ConnectError:
        print(f"Connection Error: Could not connect to server at {server_url}")
        print("Make sure the server is running and the URL is correct")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    # Get database connection string from command line argument
    connection_string = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run(connection_string))