"""Integration tests for Phase C: Package and API restructuring verification."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import app as modular_app, create_app as modular_create_app
from api.dependencies import get_manager
from api.serializers import (
    _project_name_for,
    _serialize_conflict,
    _serialize_instruction,
    _serialize_memory,
    _serialize_project,
    _serialize_session,
)
from contracts.base import Result
from recall_core import (
    ContextAssemblyService,
    CustomInstructionService,
    MemoryManager,
    create_memory_manager,
)


def test_api_package_has_zero_uow_access():
    """Verify that every python file in api/ contains zero references to private _uow."""
    api_dir = Path(__file__).resolve().parent.parent / "api"
    uow_violations: list[str] = []

    for py_file in api_dir.rglob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "_uow":
                uow_violations.append(f"{py_file.name}:{node.lineno}")

    assert not uow_violations, (
        f"Encapsulation boundary violation: Found direct _uow access in api package at: {uow_violations}"
    )


def test_canonical_api_app_initialization_and_routes():
    """Verify that canonical api.app exposes valid default app and create_app factory."""
    assert modular_app is not None

    mock_manager = Mock(spec=["list_projects_paginated", "close", "_semantic_index"])
    mock_manager.list_projects_paginated.return_value = Result.ok(Mock(items=[], total=0))
    mock_manager._semantic_index = None

    custom_app = modular_create_app(mock_manager)
    client = TestClient(custom_app)
    res = client.get("/projects")
    assert res.status_code == 200
    assert res.json() == {"projects": [], "total": 0}

    res_health = client.get("/health")
    assert res_health.status_code == 200


def test_recall_core_top_level_exports():
    """Verify that top-level recall_core package exposes the required orchestration symbols."""
    assert MemoryManager is not None
    assert create_memory_manager is not None
    assert CustomInstructionService is not None
    assert ContextAssemblyService is not None


def test_healthz_endpoint_available():
    """Verify that the /healthz liveness probe route is available and matches /health."""
    mock_manager = Mock(spec=["_semantic_index"])
    mock_manager._semantic_index = None

    app = modular_create_app(mock_manager)
    client = TestClient(app)

    res_health = client.get("/health")
    res_healthz = client.get("/healthz")

    assert res_health.status_code == 200
    assert res_healthz.status_code == 200
    assert res_healthz.json()["api_version"] == "1.0.0"


def test_pyproject_dependencies_include_python_dotenv():
    """Verify that python-dotenv is declared in root pyproject.toml dependencies."""
    import tomllib

    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    deps = data.get("project", {}).get("dependencies", [])
    assert any(
        dep.startswith("python-dotenv") for dep in deps
    ), "python-dotenv must be declared in root project dependencies"
