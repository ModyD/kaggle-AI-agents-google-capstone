-- ==========================================================
-- Neon PostgreSQL: Memories Table Migration
-- ==========================================================
-- This migration adds the 'app.memories' table for memory bank.
-- Run after 01_create_app_schema.sql
--
-- Run this migration against your Neon database:
--   psql $NEON_DATABASE_URL -f infra/02_create_memories_table.sql
-- ==========================================================

-- ==========================================================
-- app.memories - Vector memory bank for RAG and agent memory
-- ==========================================================
CREATE TABLE IF NOT EXISTS app.memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  text TEXT NOT NULL,                 -- Memory content
  embedding vector(1536),             -- Vector embedding for similarity search
  metadata JSONB DEFAULT '{}'::jsonb, -- Additional metadata
  memory_type TEXT,                   -- Type: incident, runbook, conversation, etc.
  session_id TEXT,                    -- Associated session for scoping
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Create IVFFlat index for fast vector similarity search
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class WHERE relname = 'idx_memories_embedding'
  ) THEN
    CREATE INDEX idx_memories_embedding ON app.memories
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
  END IF;
EXCEPTION
  WHEN others THEN
    RAISE NOTICE 'Could not create vector index: %', SQLERRM;
END$$;

-- Additional indexes for filtering
CREATE INDEX IF NOT EXISTS idx_memories_session ON app.memories(session_id);
CREATE INDEX IF NOT EXISTS idx_memories_type ON app.memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON app.memories(created_at);

-- ==========================================================
-- Migration complete
-- ==========================================================
DO $$
BEGIN
  RAISE NOTICE 'Migration 02_create_memories_table.sql completed successfully.';
  RAISE NOTICE 'Created table: app.memories';
END$$;
