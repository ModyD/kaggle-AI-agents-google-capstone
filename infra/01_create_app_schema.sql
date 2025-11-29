-- ==========================================================
-- Neon PostgreSQL: Application Schema Migration
-- ==========================================================
-- This migration creates the 'app' schema and all application tables.
-- IMPORTANT: Never modify the neon_auth schema (managed by Neon).
--
-- Run this migration against your Neon database:
--   psql $NEON_DATABASE_URL -f infra/01_create_app_schema.sql
--
-- Tables created:
--   - app.users      : Application users (mapped from Neon Auth)
--   - app.incidents  : Security incidents raised by users
--   - app.runbooks   : RAG memory with vector embeddings
--   - app.telemetry  : Event logs for observability
-- ==========================================================

-- Create application schema
CREATE SCHEMA IF NOT EXISTS app;

-- Enable pgvector extension (Neon supports this)
-- If this fails, runbooks.embedding column will still work but without index
CREATE EXTENSION IF NOT EXISTS vector;

-- ==========================================================
-- app.users - Application users (mapping Neon Auth → app user)
-- ==========================================================
CREATE TABLE IF NOT EXISTS app.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id TEXT UNIQUE,          -- Maps to Neon Auth user ID
  email TEXT,
  display_name TEXT,
  roles TEXT[],                       -- e.g., ['analyst', 'admin']
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ
);

-- Index for auth lookups
CREATE INDEX IF NOT EXISTS idx_users_auth_user_id ON app.users(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON app.users(email);

-- ==========================================================
-- app.incidents - Security incidents raised by users
-- ==========================================================
CREATE TABLE IF NOT EXISTS app.incidents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id TEXT UNIQUE,            -- External incident ID (e.g., INC-2024-001)
  reporter_auth_user_id TEXT,         -- Who reported this
  payload JSONB,                      -- Full incident features/data
  triage_label TEXT,                  -- CRITICAL, HIGH, MEDIUM, LOW
  triage_score FLOAT,                 -- Numeric severity score
  explanation TEXT,                   -- LLM-generated explanation
  runbook_id UUID,                    -- Reference to generated runbook
  status TEXT DEFAULT 'open',         -- open, in_progress, resolved, closed
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_incidents_incident_id ON app.incidents(incident_id);
CREATE INDEX IF NOT EXISTS idx_incidents_reporter ON app.incidents(reporter_auth_user_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON app.incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_triage_label ON app.incidents(triage_label);

-- ==========================================================
-- app.runbooks - RAG memory with vector embeddings
-- ==========================================================
-- Note: vector(1536) matches OpenAI/Gemini embedding dimensions
CREATE TABLE IF NOT EXISTS app.runbooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  text TEXT NOT NULL,                 -- Full runbook content
  embedding vector(1536),             -- Vector embedding for similarity search
  metadata JSONB DEFAULT '{}'::jsonb, -- Tags, source, version, etc.
  incident_type TEXT,                 -- e.g., brute_force, data_exfiltration
  severity TEXT,                      -- Applicable severity level
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Create IVFFlat index for fast vector similarity search
-- This index type is good for approximate nearest neighbor search
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class WHERE relname = 'idx_runbooks_embedding'
  ) THEN
    -- IVFFlat index with cosine similarity
    -- lists = 100 is good for datasets up to ~100k rows
    CREATE INDEX idx_runbooks_embedding ON app.runbooks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
  END IF;
EXCEPTION
  WHEN others THEN
    -- If vector extension not available, skip index creation
    RAISE NOTICE 'Could not create vector index: %', SQLERRM;
END$$;

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_runbooks_incident_type ON app.runbooks(incident_type);
CREATE INDEX IF NOT EXISTS idx_runbooks_severity ON app.runbooks(severity);

-- ==========================================================
-- app.telemetry - Event logs for observability
-- ==========================================================
CREATE TABLE IF NOT EXISTS app.telemetry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id TEXT,                      -- Distributed trace ID
  evt_type TEXT,                      -- Event type (e.g., triage.start, runbook.complete)
  agent_name TEXT,                    -- Which agent produced this event
  payload JSONB,                      -- Event data
  duration_ms FLOAT,                  -- Execution duration if applicable
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for querying telemetry
CREATE INDEX IF NOT EXISTS idx_telemetry_trace_id ON app.telemetry(trace_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_evt_type ON app.telemetry(evt_type);
CREATE INDEX IF NOT EXISTS idx_telemetry_created_at ON app.telemetry(created_at);

-- ==========================================================
-- app.sessions - A2A session state (optional, for Redis fallback)
-- ==========================================================
CREATE TABLE IF NOT EXISTS app.sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT UNIQUE NOT NULL,
  incident_id TEXT,
  state JSONB DEFAULT '{}'::jsonb,
  timeline JSONB DEFAULT '[]'::jsonb,  -- A2A message timeline
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON app.sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_incident_id ON app.sessions(incident_id);

-- ==========================================================
-- Grants (optional - for application role)
-- ==========================================================
-- If you have a separate application role, grant permissions:
-- GRANT USAGE ON SCHEMA app TO your_app_role;
-- GRANT ALL ON ALL TABLES IN SCHEMA app TO your_app_role;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA app TO your_app_role;

-- ==========================================================
-- Migration complete
-- ==========================================================
DO $$
BEGIN
  RAISE NOTICE 'Migration 01_create_app_schema.sql completed successfully.';
  RAISE NOTICE 'Created schema: app';
  RAISE NOTICE 'Created tables: app.users, app.incidents, app.runbooks, app.telemetry, app.sessions';
END$$;
