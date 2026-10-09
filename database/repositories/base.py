"""Base utilities for SQLite repository implementations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from contracts.base import Scope, MemoryStatus, InstructionStatus
from contracts.instruction import CustomInstruction
from contracts.memory import Memory, MemoryStatus as ContractMemoryStatus
from contracts.project import Project, Session


def row_to_uuid(value: Any) -> Optional[UUID]:
    """Convert a database value to UUID."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(value)


def row_to_datetime(value: Any) -> Optional[datetime]:
    """Convert a database value to datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # SQLite stores datetime as TEXT in ISO format
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def row_to_dict(value: Any) -> dict[str, Any]:
    """Convert a database JSON value to dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def uuid_to_str(value: Optional[UUID]) -> Optional[str]:
    """Convert UUID to string for database storage."""
    if value is None:
        return None
    return str(value)


def datetime_to_str(value: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO format string for database storage."""
    if value is None:
        return None
    return value.isoformat()


def scope_to_str(scope: Scope) -> str:
    """Convert Scope enum to string."""
    return scope.value


def str_to_scope(value: str) -> Scope:
    """Convert string to Scope enum."""
    return Scope(value)


def memory_status_to_str(status: ContractMemoryStatus) -> str:
    """Convert MemoryStatus enum to string."""
    return status.value


def str_to_memory_status(value: str) -> ContractMemoryStatus:
    """Convert string to MemoryStatus enum."""
    return ContractMemoryStatus(value)


def instruction_status_to_str(status: InstructionStatus) -> str:
    """Convert InstructionStatus enum to string."""
    return status.value


def str_to_instruction_status(value: str) -> InstructionStatus:
    """Convert string to InstructionStatus enum."""
    return InstructionStatus(value)


def dict_to_json(value: dict[str, Any]) -> str:
    """Convert dict to JSON string for database storage."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def project_row_to_dto(row: dict[str, Any]) -> Project:
    """Convert a database row to Project DTO."""
    return Project(
        id=row_to_uuid(row["project_id"]),
        name=row["name"],
        description=row["description"],
        metadata=row_to_dict(row["metadata"]),
        created_at=row_to_datetime(row["created_at"]),
        updated_at=row_to_datetime(row["updated_at"]),
    )


def session_row_to_dto(row: dict[str, Any]) -> Session:
    """Convert a database row to Session DTO."""
    return Session(
        id=row_to_uuid(row["session_id"]),
        project_id=row_to_uuid(row["project_id"]),
        started_at=row_to_datetime(row["started_at"]),
        ended_at=row_to_datetime(row["ended_at"]),
        metadata=row_to_dict(row["metadata"]),
        created_at=row_to_datetime(row["created_at"]),
        updated_at=row_to_datetime(row["updated_at"]),
    )


def memory_row_to_dto(row: dict[str, Any]) -> Memory:
    """Convert a database row to Memory DTO."""
    return Memory(
        id=row_to_uuid(row["memory_id"]),
        project_id=row_to_uuid(row["project_id"]),
        session_id=row_to_uuid(row["session_id"]),
        scope=str_to_scope(row["scope"]),
        memory_type=row["memory_type"],
        content=row["content"],
        status=str_to_memory_status(row["status"]),
        provenance=row["provenance"],
        supersedes_id=row_to_uuid(row["supersedes_id"]),
        metadata=row_to_dict(row["metadata"]),
        created_at=row_to_datetime(row["created_at"]),
        updated_at=row_to_datetime(row["updated_at"]),
    )


def instruction_row_to_dto(row: dict[str, Any]) -> CustomInstruction:
    """Convert a database row to CustomInstruction DTO."""
    return CustomInstruction(
        id=row_to_uuid(row["instruction_id"]),
        scope=str_to_scope(row["scope"]),
        project_id=row_to_uuid(row["project_id"]),
        content=row["content"],
        status=str_to_instruction_status(row["status"]),
        version=row["version"],
        metadata=row_to_dict(row["metadata"]),
        created_at=row_to_datetime(row["created_at"]),
        updated_at=row_to_datetime(row["updated_at"]),
    )