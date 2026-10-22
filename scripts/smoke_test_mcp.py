"""Developer smoke test script for running FastMCP server functions directly.

Usage:
    python scripts/smoke_test_mcp.py [--project-id <UUID>] [--query <text>]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.project import ProjectCreateRequest
from recall_core.bootstrap import create_memory_manager
from recall_mcp.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test RECALL FastMCP tools directly")
    parser.add_argument(
        "--project-id",
        default=os.getenv("RECALL_PROJECT_ID"),
        help="Target project UUID (uses first existing project or creates a test project if omitted)",
    )
    parser.add_argument(
        "--query",
        default="retrieve what is stored in memory",
        help="Query string for search test",
    )
    parser.add_argument(
        "--isolated",
        action="store_true",
        default=os.getenv("RECALL_SMOKE_ISOLATED", "false").lower() in ("true", "1", "yes"),
        help="Run smoke test in an isolated temporary database to protect live storage",
    )
    args = parser.parse_args()

    temp_dir_obj = None
    old_db_path = os.environ.get("RECALL_DB_PATH")
    if args.isolated:
        import tempfile
        temp_dir_obj = tempfile.TemporaryDirectory()
        temp_db = Path(temp_dir_obj.name) / "recall_smoke.sqlite3"
        os.environ["RECALL_DB_PATH"] = str(temp_db)
        print(f"[SMOKE] Running isolated test with temporary database: {temp_db}")

    print("Initializing MemoryManager and FastMCP Server...")
    memory_manager = create_memory_manager()
    server = create_server(memory_manager)

    try:
        project_uuid: UUID | None = None
        if args.project_id:
            try:
                project_uuid = UUID(args.project_id)
            except ValueError:
                print(f"Invalid UUID: {args.project_id}", file=sys.stderr)
                sys.exit(1)
        else:
            # Query existing projects from manager using public API
            projects_result = memory_manager.list_projects(limit=1)
            if projects_result and projects_result.success and projects_result.value:
                project_uuid = projects_result.value[0].id
                print(f"Using existing project: {projects_result.value[0].name} ({project_uuid})")
            else:
                # Create a temporary project for the smoke test
                created = memory_manager.create_project(ProjectCreateRequest(name="Smoke Test Project", description="Temporary test project"))
                if created.success and created.value:
                    project_uuid = created.value.id
                    print(f"Created temporary project: {project_uuid}")
                else:
                    print("Failed to find or create a project for smoke testing", file=sys.stderr)
                    sys.exit(1)

        print(f"\n--- TEST 1: recall_search (project_id={project_uuid}) ---")
        search_tool = server._tool_manager.get_tool("recall_search")
        res_search = search_tool.fn(
            query=args.query,
            project_id=str(project_uuid),
            session_id=None,
            limit=5,
        )
        print(f"Results found: {res_search.get('total_found')}")

        print(f"\n--- TEST 2: recall_get_context (project_id={project_uuid}) ---")
        context_tool = server._tool_manager.get_tool("recall_get_context")
        res_context = context_tool.fn(
            project_id=str(project_uuid),
            query=args.query,
            limit=5,
        )
        print(f"Active memories in context: {len(res_context.get('active_memories', []))}")
        print("\nSmoke test completed successfully.")
    finally:
        if memory_manager is not None:
            memory_manager.close()
        if temp_dir_obj is not None:
            if old_db_path is not None:
                os.environ["RECALL_DB_PATH"] = old_db_path
            else:
                os.environ.pop("RECALL_DB_PATH", None)
            try:
                temp_dir_obj.cleanup()
                print("[SMOKE] Isolated temporary test database cleaned up successfully.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
