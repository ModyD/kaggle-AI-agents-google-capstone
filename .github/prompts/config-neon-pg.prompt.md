---
agent: agent
model: Claude Opus 4.5 (Preview) (copilot)
---
You are building the backend database layer of my project.  
I am using Neon PostgreSQL with Neon Auth enabled. Check .env for connection details to my neon.  
Here is the current database state:

- Schemas present:
    neon_auth (system / managed by Neon)
    public (empty)
- No application tables exist
- I MUST NOT modify or write tables inside neon_auth
- I MUST create my own schema “app” and all tables inside it

Now generate the FULL implementation for my app-side database layer, including:

==========================================================
1. SQL MIGRATION FILE (create schema + tables)
==========================================================
Create a SQL file at:
    infra/01_create_app_schema.sql

Contents:
- Create schema app
- Create tables:
    app.users
    app.incidents
    app.runbooks
    app.telemetry
- Ensure pgvector extension exists if possible
- Use embedding vector(1536) for runbooks table
- Include fallback comments if extension is unavailable
- Make all tables idempotent (IF NOT EXISTS)
- NEVER modify neon_auth schema

Here is the exact SQL you must place inside the file:

----------------------------------------------------------
-- create schema
CREATE SCHEMA IF NOT EXISTS app;

-- enable vector extension (safe)
CREATE EXTENSION IF NOT EXISTS vector;

-- application users table (mapping Neon auth → app user)
CREATE TABLE IF NOT EXISTS app.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id TEXT UNIQUE,
  email TEXT,
  display_name TEXT,
  roles TEXT[],
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ
);

-- incidents raised by users
CREATE TABLE IF NOT EXISTS app.incidents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id TEXT UNIQUE,
  reporter_auth_user_id TEXT,
  payload JSONB,
  triage_label TEXT,
  triage_score FLOAT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- runbooks / memory (RAG)
CREATE TABLE IF NOT EXISTS app.runbooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  text TEXT NOT NULL,
  embedding vector(1536),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- optional index (if vector index allowed)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class WHERE relname = 'idx_runbooks_embedding'
  ) THEN
    CREATE INDEX idx_runbooks_embedding ON app.runbooks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
  END IF;
END$$;

-- telemetry event logs
CREATE TABLE IF NOT EXISTS app.telemetry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id TEXT,
  evt_type TEXT,
  payload JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
----------------------------------------------------------


==========================================================
2. PYTHON FILES FOR DB INITIALIZATION & USER UPSERT
==========================================================
Create file: backend/app/db.py
Include:

- Settings loader (Pydantic)
- Asyncpg connection pool initialization
- aioredis client init
- get_pg_conn dependency
- Upsert helper to insert/update users after OAuth login

Upsert helper signature:
    async def upsert_user(conn, auth_user_id, email, display_name, roles=None, metadata=None)

Upsert logic:
INSERT INTO app.users (...) VALUES (...)
ON CONFLICT(auth_user_id) DO UPDATE SET email = EXCLUDED.email,
display_name = EXCLUDED.display_name, roles = EXCLUDED.roles,
metadata = app.users.metadata || EXCLUDED.metadata,
last_seen = now()

Add docstrings and logging placeholders.


==========================================================
3. TEST SCRIPT TO VALIDATE NEON CONNECTION & USER UPSERT
==========================================================
Create file:
    backend/scripts/test_neon_connection.py

Content:
- Load NEON_DATABASE_URL from env
- Connect using asyncpg
- Print count(*) from app.users
- Run upsert_user() with test values
- Print inserted row


==========================================================
4. UPDATE app/main.py STARTUP/SHUTDOWN HOOKS
==========================================================
Add instructions in comments (not full file rewrite):
- Import init_pg_pool, init_redis, close_pg_pool, close_redis from app.db
- In @app.on_event("startup"): call init_pg_pool(app), init_redis(app)
- In @app.on_event("shutdown"): call close_pg_pool(app), close_redis(app)


==========================================================
5. OUTPUT FORMAT
==========================================================
When generating all files:
- Create directories as needed
- Output the actual file contents
- Do not invent new schemas or tables
- Do not alter neon_auth
- Keep everything deterministic and ready to apply

Begin now.
