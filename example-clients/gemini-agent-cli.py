#!/usr/bin/env python
# example-clients/gemini-agent-cli.py
import asyncio
import argparse
import os
import json
import codecs
import sys
import dotenv
from mcp import ClientSession
from mcp.client.sse import sse_client
from tabulate import tabulate
from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from httpx import AsyncClient

# Load environment variables
dotenv.load_dotenv()

# Default values
DEFAULT_MCP_URL = os.getenv("PG_MCP_URL", "http://localhost:8000/sse")
DEFAULT_DB_URL = os.getenv("DATABASE_URL", "")
DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY", "")

class AgentCLI:
    def __init__(self, mcp_url, db_url, api_key):
        self.mcp_url = mcp_url
        self.db_url = db_url
        self.api_key = api_key
        self.conn_id = None
        
        custom_http_client = AsyncClient(timeout=30)
        model = GeminiModel(
            'gemini-2.0-flash',
            provider=GoogleGLAProvider(api_key=api_key, http_client=custom_http_client),
        )
        self.agent = Agent(model)
    
    async def initialize(self):
        """Initialize the session and connect to the database."""
        print(f"Connecting to MCP server at {self.mcp_url}...")
        async with sse_client(url=self.mcp_url) as streams:
            async with ClientSession(*streams) as self.session:
                await self.session.initialize()

                # Connect to database
                if not self.db_url:
                    self.db_url = input("Enter PostgreSQL connection URL: ")
                
                try:
                    connect_result = await self.session.call_tool(
                        "connect",
                        {"connection_string": self.db_url}
                    )
                    
                    if hasattr(connect_result, 'content') and connect_result.content:
                        content = connect_result.content[0]
                        if hasattr(content, 'text'):
                            result_data = json.loads(content.text)
                            self.conn_id = result_data.get('conn_id')
                            print(f"Connected to database with ID: {self.conn_id}")
                        else:
                            print("Error: Connection response missing text content")
                            return
                    else:
                        print("Error: Connection response missing content")
                        return
                except Exception as e:
                    print(f"Error establishing connection to database: {e}")
                    return
                
                # Main interaction loop
                while True:
                    try:
                        await self.process_user_query()
                    except KeyboardInterrupt:
                        print("\nDisconnecting from database...")
                        try:
                            if self.conn_id:
                                await self.session.call_tool(
                                    "disconnect",
                                    {"conn_id": self.conn_id}
                                )
                                print("Successfully disconnected.")
                        except Exception as e:
                            print(f"Error during disconnect: {e}")
                        finally:
                            print("Exiting.")
                            return
    
    async def process_user_query(self):
        """Process a natural language query from the user."""
        if not self.conn_id:
            print("Error: Not connected to database")
            return
            
        # Get the user's natural language query
        print("\n--------------------------------------------------")
        user_query = input("Enter your question (or 'exit' to quit): ")
        
        if user_query.lower() in ['exit', 'quit']:
            raise KeyboardInterrupt()
        
        print("Generating SQL query...")
        
        try:
            # Get the prompt from server
            prompt_response = await self.session.get_prompt('generate_sql', {
                'conn_id': self.conn_id,
                'nl_query': user_query
            })
            
            # Extract messages from prompt response
            if not hasattr(prompt_response, 'messages') or not prompt_response.messages:
                print("Error: Invalid prompt response from server")
                return
            
            # Convert MCP messages to format expected by Gemini
            messages = []
            for msg in prompt_response.messages:
                messages.append({
                    "role": msg.role,
                    "content": msg.content.text if hasattr(msg.content, 'text') else str(msg.content)
                })
            
            # Use the agent with the formatted messages
            response = await self.agent.run(str(messages))
            
            # Access the response content
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Extract SQL from response
            sql_query = None
            
            # Look for SQL in code blocks
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
                print("\nCould not extract SQL from the response.")
                print("Response:", response_text[:100] + "..." if len(response_text) > 100 else response_text)
                return
            
            # Add trailing semicolon if missing
            sql_query = sql_query.strip()
            if not sql_query.endswith(';'):
                sql_query = sql_query + ';'
            
            # Handle escaped characters
            unescaped_sql_query = codecs.decode(sql_query, 'unicode_escape')
            
            # Display and confirm
            print("\nGenerated SQL query:")
            print(unescaped_sql_query)
            
            execute = input("\nDo you want to execute this query? (y/n): ")
            if execute.lower() != 'y':
                return
            
            # Execute the query
            print("Executing query...")
            result = await self.session.call_tool(
                "pg_query",
                {
                    "query": unescaped_sql_query,
                    "conn_id": self.conn_id
                }
            )
            
            # Process results
            if hasattr(result, 'content') and result.content:
                query_results = []
                
                # Extract all content items and parse the JSON
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        try:
                            # Parse each row from JSON
                            row_data = json.loads(content_item.text)
                            if isinstance(row_data, list):
                                query_results.extend(row_data)
                            else:
                                query_results.append(row_data)
                        except json.JSONDecodeError:
                            print(f"Error parsing result item: {content_item.text[:100]}")
                
                # Display the formatted results
                if query_results:
                    print("\nQuery Results:")
                    table = tabulate(
                        query_results,
                        headers="keys",
                        tablefmt="pretty"
                    )
                    print(table)
                    print(f"\nTotal rows: {len(query_results)}")
                else:
                    print("\nQuery executed successfully but returned no results.")
            else:
                print("Query executed but no content returned")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

async def main():
    parser = argparse.ArgumentParser(description="Natural Language to SQL CLI for PG-MCP")
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL, help="MCP server URL")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="PostgreSQL connection URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Gemini API key")
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("Error: Gemini API key is required")
        print("Set GEMINI_API_KEY in .env file or provide via --api-key argument")
        sys.exit(1)
    
    agent = AgentCLI(args.mcp_url, args.db_url, args.api_key)
    await agent.initialize()

if __name__ == "__main__":
    asyncio.run(main())