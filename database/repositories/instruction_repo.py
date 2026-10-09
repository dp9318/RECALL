"""SQLite implementation of CustomInstructionRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional
from uuid import UUID

from contracts.base import PaginatedResult, PaginationParams, Result
from contracts.instruction import (
    CustomInstruction,
    CustomInstructionCreateRequest,
    CustomInstructionListParams,
    CustomInstructionUpdateRequest,
    InstructionStatus,
)
from database.repositories import CustomInstructionRepository
from database.repositories.base import (
    instruction_row_to_dto,
    datetime_to_str,
    dict_to_json,
    uuid_to_str,
    row_to_dict,
    row_to_uuid,
    row_to_datetime,
)


class SQLiteCustomInstructionRepository(CustomInstructionRepository):
    """SQLite implementation of CustomInstructionRepository."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, request: CustomInstructionCreateRequest) -> Result[CustomInstruction]:
        """Create a new custom instruction."""
        from uuid import uuid4
        instruction = CustomInstruction(
            id=request.id if hasattr(request, "id") and request.id else uuid4(),
            scope=request.scope,
            project_id=request.project_id,
            content=request.content,
            metadata=request.metadata,
        )

        try:
            with self._conn:
                # Check uniqueness for project-scoped active instructions
                if instruction.scope.value == "project" and instruction.project_id:
                    cursor = self._conn.execute(
                        """
                        SELECT instruction_id FROM custom_instructions
                        WHERE scope = 'project' AND project_id = ? AND status = 'active'
                        """,
                        (uuid_to_str(instruction.project_id),),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        return Result.err(
                            f"Active project-scoped instruction already exists for project {instruction.project_id}"
                        )

                self._conn.execute(
                    """
                    INSERT INTO custom_instructions (
                        instruction_id, scope, project_id, content, status, version,
                        metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid_to_str(instruction.id),
                        instruction.scope.value,
                        uuid_to_str(instruction.project_id),
                        instruction.content,
                        InstructionStatus.ACTIVE.value,
                        instruction.version,
                        dict_to_json(instruction.metadata),
                        datetime_to_str(instruction.created_at),
                        datetime_to_str(instruction.updated_at),
                    ),
                )

            return Result.ok(instruction)
        except sqlite3.IntegrityError as e:
            return Result.err(f"Instruction creation failed: {e}")
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def get(self, instruction_id: UUID) -> Result[Optional[CustomInstruction]]:
        """Get a custom instruction by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM custom_instructions WHERE instruction_id = ?",
            (uuid_to_str(instruction_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return Result.ok(None)
        return Result.ok(instruction_row_to_dto(dict(row)))

    def update(self, instruction_id: UUID, request: CustomInstructionUpdateRequest) -> Result[Optional[CustomInstruction]]:
        """Update a custom instruction."""
        existing = self.get(instruction_id)
        if not existing.success or existing.value is None:
            return Result.ok(None)

        instruction = existing.value
        updated_content = request.content if request.content is not None else instruction.content
        updated_status = request.status if request.status is not None else instruction.status
        updated_metadata = request.metadata if request.metadata is not None else instruction.metadata

        try:
            with self._conn:
                # Check uniqueness if activating a project-scoped instruction
                if updated_status == InstructionStatus.ACTIVE and instruction.scope.value == "project" and instruction.project_id:
                    cursor = self._conn.execute(
                        """
                        SELECT instruction_id FROM custom_instructions
                        WHERE scope = 'project' AND project_id = ? AND status = 'active'
                        AND instruction_id != ?
                        """,
                        (uuid_to_str(instruction.project_id), uuid_to_str(instruction_id)),
                    )
                    existing_active = cursor.fetchone()
                    if existing_active:
                        return Result.err(
                            f"Active project-scoped instruction already exists for project {instruction.project_id}"
                        )

                self._conn.execute(
                    """
                    UPDATE custom_instructions
                    SET content = ?, status = ?, metadata = ?, version = version + 1, updated_at = ?
                    WHERE instruction_id = ?
                    """,
                    (
                        updated_content,
                        updated_status.value if hasattr(updated_status, 'value') else updated_status,
                        dict_to_json(updated_metadata),
                        datetime.now().isoformat(),
                        uuid_to_str(instruction_id),
                    ),
                )
                self._conn.commit()

            return self.get(instruction_id)
        except sqlite3.IntegrityError as e:
            return Result.err(f"Instruction update failed: {e}")
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def delete(self, instruction_id: UUID) -> Result[bool]:
        """Delete (deactivate) a custom instruction."""
        try:
            cursor = self._conn.execute(
                """
                UPDATE custom_instructions
                SET status = ?, updated_at = ?
                WHERE instruction_id = ?
                """,
                (InstructionStatus.DELETED.value, datetime.now().isoformat(), uuid_to_str(instruction_id)),
            )
            self._conn.commit()
            return Result.ok(cursor.rowcount > 0)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def list(self, params: CustomInstructionListParams) -> Result[PaginatedResult[CustomInstruction]]:
        """List custom instructions with filters."""
        try:
            conditions = []
            values = []

            if params.scope:
                conditions.append("scope = ?")
                values.append(params.scope.value)

            if params.project_id:
                conditions.append("project_id = ?")
                values.append(uuid_to_str(params.project_id))

            if params.status:
                conditions.append("status = ?")
                values.append(params.status.value)

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            # Count total
            count_sql = f"SELECT COUNT(*) FROM custom_instructions {where_clause}"
            count_cursor = self._conn.execute(count_sql, values)
            total = count_cursor.fetchone()[0]

            # Get paginated results
            sql = f"""
                SELECT * FROM custom_instructions
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            values.extend([params.limit, params.offset])

            cursor = self._conn.execute(sql, values)
            instructions = [instruction_row_to_dto(dict(row)) for row in cursor.fetchall()]

            return Result.ok(PaginatedResult(
                items=instructions,
                total=total,
                limit=params.limit,
                offset=params.offset,
            ))
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def get_active_for_scope(self, scope: str, project_id: Optional[UUID] = None) -> Result[list[CustomInstruction]]:
        """Get active instructions for a scope."""
        try:
            if scope == "global":
                cursor = self._conn.execute(
                    """
                    SELECT * FROM custom_instructions
                    WHERE scope = 'global' AND status = 'active'
                    ORDER BY created_at DESC
                    """
                )
            elif scope == "project" and project_id:
                cursor = self._conn.execute(
                    """
                    SELECT * FROM custom_instructions
                    WHERE scope = 'project' AND project_id = ? AND status = 'active'
                    ORDER BY created_at DESC
                    """,
                    (uuid_to_str(project_id),),
                )
            else:
                return Result.ok([])

            rows = cursor.fetchall()
            instructions = [instruction_row_to_dto(dict(row)) for row in rows]
            return Result.ok(instructions)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")