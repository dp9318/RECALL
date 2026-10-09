-- Migration 002: Add partial unique index for active project-scoped custom instructions
-- This enforces the uniqueness constraint: at most one active project-scoped instruction per project

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_instructions_unique_active_project
ON custom_instructions (scope, project_id)
WHERE status = 'active' AND scope = 'project';