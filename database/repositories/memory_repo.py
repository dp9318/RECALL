"""SQLite implementation of MemoryRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from contracts.base import PaginatedResult, PaginationParams, Result, Scope
from contracts.memory import (
    Memory,
    MemoryCreateRequest,
    MemoryLineage,
    MemorySearchParams,
    MemoryStatus,
    MemoryUpdateRequest,
)
from database.repositories import MemoryRepository
from database.repositories.base import (
    datetime_to_str,
    dict_to_json,
    uuid_to_str,
    row_to_dict,
    row_to_uuid,
    row_to_datetime,
)


class SQLiteMemoryRepository(MemoryRepository):
    """SQLite implementation of MemoryRepository."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, request: MemoryCreateRequest) -> Result[Memory]:
        """Create a new memory."""
        memory = Memory(
            id=request.id if hasattr(request, "id") and request.id else UUID(int=0),
            project_id=request.project_id,
            session_id=request.session_id,
            scope=request.scope,
            memory_type=request.memory_type,
            content=request.content,
            provenance=request.provenance,
            supersedes_id=request.supersedes_id,
            metadata=request.metadata,
        )
        if memory.id == UUID(int=0):
            from uuid import uuid4
            memory = Memory(
                id=uuid4(),
                project_id=request.project_id,
                session_id=request.session_id,
                scope=request.scope,
                memory_type=request.memory_type,
                content=request.content,
                provenance=request.provenance,
                supersedes_id=request.supersedes_id,
                metadata=request.metadata,
            )

        try:
            self._conn.execute(
                """
                INSERT INTO memories (
                    memory_id, project_id, session_id, scope, memory_type,
                    content, status, provenance, supersedes_id,
                    valid_from, valid_until, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid_to_str(memory.id),
                    uuid_to_str(memory.project_id),
                    uuid_to_str(memory.session_id),
                    memory.scope.value,
                    memory.memory_type,
                    memory.content,
                    MemoryStatus.ACTIVE.value,
                    memory.provenance,
                    uuid_to_str(memory.supersedes_id),
                    datetime_to_str(getattr(memory, 'valid_from', None)),
                    datetime_to_str(getattr(memory, 'valid_until', None)),
                    datetime_to_str(memory.created_at),
                    datetime_to_str(memory.updated_at),
                    dict_to_json(memory.metadata),
                ),
            )

            # If this memory supersedes another, update the old memory's status
            if memory.supersedes_id:
                self._conn.execute(
                    """
                    UPDATE memories
                    SET status = ?, updated_at = ?
                    WHERE memory_id = ?
                    """,
                    (MemoryStatus.SUPERSEDED.value, datetime.now().isoformat(), uuid_to_str(memory.supersedes_id)),
                )

                # Create lineage record
                from uuid import uuid4
                lineage = MemoryLineage(
                    id=uuid4(),
                    parent_id=memory.supersedes_id,
                    child_id=memory.id,
                    relationship="supersedes",
                    reason="explicit_user_update",
                )
                self._conn.execute(
                    """
                    INSERT INTO memory_lineage (lineage_id, parent_id, child_id, relationship, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid_to_str(lineage.id),
                        uuid_to_str(lineage.parent_id),
                        uuid_to_str(lineage.child_id),
                        lineage.relationship,
                        lineage.reason,
                        datetime.now().isoformat(),
                    ),
                )

            # Note: Transaction commit is managed by the caller (UnitOfWork/transaction context)
            return Result.ok(memory)
        except sqlite3.IntegrityError as e:
            return Result.err(f"Memory creation failed: {e}")
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def get(self, memory_id: UUID) -> Result[Optional[Memory]]:
        """Get a memory by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM memories WHERE memory_id = ?",
            (uuid_to_str(memory_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return Result.ok(None)
        return Result.ok(self._row_to_memory(dict(row)))

    def _row_to_memory(self, row: dict[str, Any]) -> Memory:
        """Convert a database row to Memory DTO."""
        from database.repositories.base import (
            row_to_uuid,
            row_to_datetime,
            row_to_dict,
        )
        return Memory(
            id=row_to_uuid(row["memory_id"]),
            project_id=row_to_uuid(row["project_id"]),
            session_id=row_to_uuid(row["session_id"]),
            scope=Scope(row["scope"]),
            memory_type=row["memory_type"],
            content=row["content"],
            status=MemoryStatus(row["status"]),
            provenance=row["provenance"],
            supersedes_id=row_to_uuid(row["supersedes_id"]),
            metadata=row_to_dict(row["metadata"]),
            created_at=row_to_datetime(row["created_at"]),
            updated_at=row_to_datetime(row["updated_at"]),
        )

    def update(self, memory_id: UUID, request: MemoryUpdateRequest) -> Result[Optional[Memory]]:
        """Update a memory."""
        existing = self.get(memory_id)
        if not existing.success or existing.value is None:
            return Result.ok(None)

        memory = existing.value
        updated_content = request.content if request.content is not None else memory.content
        updated_status = request.status if request.status is not None else memory.status
        updated_metadata = request.metadata if request.metadata is not None else memory.metadata
        updated_supersedes_id = request.supersedes_id if request.supersedes_id is not None else memory.supersedes_id

        try:
            self._conn.execute(
                """
                UPDATE memories
                SET content = ?, status = ?, metadata = ?, supersedes_id = ?, updated_at = ?
                WHERE memory_id = ?
                """,
                (
                    updated_content,
                    updated_status.value if hasattr(updated_status, 'value') else updated_status,
                    dict_to_json(request.metadata) if request.metadata else "{}",
                    uuid_to_str(updated_supersedes_id),
                    datetime.now().isoformat(),
                    uuid_to_str(memory_id),
                ),
            )
            # Note: Transaction commit is managed by the caller (UnitOfWork/transaction context)

            return self.get(memory_id)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def delete(self, memory_id: UUID) -> Result[bool]:
        """Delete (deactivate) a memory."""
        try:
            cursor = self._conn.execute(
                """
                UPDATE memories
                SET status = ?, updated_at = ?
                WHERE memory_id = ?
                """,
                (MemoryStatus.DELETED.value, datetime.now().isoformat(), uuid_to_str(memory_id)),
            )
            # Note: Transaction commit is managed by the caller (UnitOfWork/transaction context)
            return Result.ok(cursor.rowcount > 0)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def search(self, params: MemorySearchParams) -> Result[PaginatedResult[Memory]]:
        """Search memories with filters."""
        try:
            conditions = []
            values = []

            if params.query:
                conditions.append("content LIKE ?")
                values.append(f"%{params.query}%")

            if params.project_id:
                conditions.append("project_id = ?")
                values.append(uuid_to_str(params.project_id))

            if params.session_id:
                conditions.append("session_id = ?")
                values.append(uuid_to_str(params.session_id))

            if params.scope:
                conditions.append("scope = ?")
                values.append(params.scope.value)

            if params.memory_type:
                conditions.append("memory_type = ?")
                values.append(params.memory_type)

            if params.status:
                conditions.append("status = ?")
                values.append(params.status.value)

            if not params.include_historical and params.status != MemoryStatus.DELETED:
                conditions.append("status != ?")
                values.append(MemoryStatus.DELETED.value)

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            # Count total
            count_sql = f"SELECT COUNT(*) FROM memories {where_clause}"
            count_cursor = self._conn.execute(count_sql, values)
            total = count_cursor.fetchone()[0]

            # Get paginated results
            sql = f"""
                SELECT * FROM memories
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            values.extend([params.limit, params.offset])

            cursor = self._conn.execute(sql, values)
            memories = [self._row_to_memory(dict(row)) for row in cursor.fetchall()]

            return Result.ok(PaginatedResult(
                items=memories,
                total=total,
                limit=params.limit,
                offset=params.offset,
            ))
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def get_active_for_project(self, project_id: UUID, limit: int = 50) -> Result[list[Memory]]:
        """Get active memories for a project."""
        try:
            cursor = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE project_id = ? AND status = 'active'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (uuid_to_str(project_id), limit),
            )
            rows = cursor.fetchall()
            memories = [self._row_to_memory(dict(row)) for row in rows]
            return Result.ok(memories)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def get_by_ids(self, memory_ids: list[UUID]) -> Result[list[Memory]]:
        """Get memories by IDs."""
        if not memory_ids:
            return Result.ok([])

        try:
            placeholders = ",".join(["?"] * len(memory_ids))
            values = [uuid_to_str(mid) for mid in memory_ids]
            cursor = self._conn.execute(
                f"SELECT * FROM memories WHERE memory_id IN ({placeholders})",
                values,
            )
            memories = [self._row_to_memory(dict(row)) for row in cursor.fetchall()]
            return Result.ok(memories)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def create_lineage(self, lineage: MemoryLineage) -> Result[MemoryLineage]:
        """Create a lineage record."""
        from uuid import uuid4
        if lineage.id == UUID(int=0):
            lineage = MemoryLineage(
                id=uuid4(),
                parent_id=lineage.parent_id,
                child_id=lineage.child_id,
                relationship=lineage.relationship,
                reason=lineage.reason,
            )

        try:
            self._conn.execute(
                """
                INSERT INTO memory_lineage (lineage_id, parent_id, child_id, relationship, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid_to_str(lineage.id),
                    uuid_to_str(lineage.parent_id),
                    uuid_to_str(lineage.child_id),
                    lineage.relationship,
                    lineage.reason,
                    datetime.now().isoformat(),
                ),
            )
            self._conn.commit()
            return Result.ok(lineage)
        except sqlite3.IntegrityError as e:
            return Result.err(f"Lineage creation failed: {e}")
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def get_lineage(self, memory_id: UUID) -> Result[list[MemoryLineage]]:
        """Get lineage for a memory."""
        try:
            cursor = self._conn.execute(
                """
                SELECT * FROM memory_lineage
                WHERE parent_id = ? OR child_id = ?
                ORDER BY created_at
                """,
                (uuid_to_str(memory_id), uuid_to_str(memory_id)),
            )
            rows = cursor.fetchall()
            lineage = []
            for row in rows:
                lineage.append(MemoryLineage(
                    id=row_to_uuid(row["lineage_id"]),
                    parent_id=row_to_uuid(row["parent_id"]),
                    child_id=row_to_uuid(row["child_id"]),
                    relationship=row["relationship"],
                    reason=row["reason"],
                    created_at=row_to_datetime(row["created_at"]),
                ))
            return Result.ok(lineage)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")