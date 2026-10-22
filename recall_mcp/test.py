"""Test script for running server functions directly with the new detailed timing logs.

Run with Python 3.12:
    C:\\Users\\dipan\\AppData\\Local\\Programs\\Python\\Python312\\python.exe recall_mcp/test.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.recall_core.bootstrap import create_memory_manager
from recall_mcp.server import create_server

print("Initializing MemoryManager and Server...")
memory_manager = create_memory_manager()
server = create_server(memory_manager)

# Access the wrapped tool directly from FastMCP
print("\n--- TEST 1: recall_search ---")
res_search = server._tool_manager.get_tool("recall_search").fn(
    query="retrieve what is stored in memory",
    project_id="195081f5-657b-47fc-a578-57ce84464f75",
    session_id=None,
    limit=5,
)
print(f"Results found: {res_search.get('total_found')}")

print("\n--- TEST 2: recall_get_context ---")
res_context = server._tool_manager.get_tool("recall_get_context").fn(
    project_id="195081f5-657b-47fc-a578-57ce84464f75",
    query="what projects did dipankar work on",
    limit=5,
)
print(f"Active memories in context: {len(res_context.get('active_memories', []))}")

memory_manager.close()
print("\nTest completed successfully.")