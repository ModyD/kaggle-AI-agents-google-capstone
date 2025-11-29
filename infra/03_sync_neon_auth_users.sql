-- ==========================================================
-- Neon PostgreSQL: Auto-sync Neon Auth users to app.users
-- ==========================================================
-- This migration creates a trigger to automatically sync users
-- from neon_auth.users_sync to app.users when they sign up or update.
--
-- Run this migration against your Neon database:
--   psql $NEON_DATABASE_URL -f infra/03_sync_neon_auth_users.sql
-- ==========================================================

-- ==========================================================
-- Function: Sync user from neon_auth to app.users
-- ==========================================================
CREATE OR REPLACE FUNCTION app.sync_user_from_neon_auth()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO app.users (
        auth_user_id,
        email,
        display_name,
        roles,
        metadata,
        last_seen
    )
    VALUES (
        NEW.id,
        NEW.email,
        NEW.name,
        ARRAY['user']::TEXT[],  -- Default role
        jsonb_build_object(
            'synced_from', 'neon_auth',
            'synced_at', now(),
            'raw_json_keys', (SELECT array_agg(key) FROM jsonb_object_keys(NEW.raw_json) AS key)
        ),
        now()
    )
    ON CONFLICT (auth_user_id) DO UPDATE SET
        email = EXCLUDED.email,
        display_name = EXCLUDED.display_name,
        metadata = app.users.metadata || jsonb_build_object('last_sync', now()),
        last_seen = now();
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================================
-- Trigger: Auto-sync on insert/update to neon_auth.users_sync
-- ==========================================================
DROP TRIGGER IF EXISTS sync_neon_auth_to_app_users ON neon_auth.users_sync;

CREATE TRIGGER sync_neon_auth_to_app_users
    AFTER INSERT OR UPDATE ON neon_auth.users_sync
    FOR EACH ROW
    EXECUTE FUNCTION app.sync_user_from_neon_auth();

-- ==========================================================
-- Initial sync: Copy existing users from neon_auth to app.users
-- ==========================================================
INSERT INTO app.users (auth_user_id, email, display_name, roles, metadata, last_seen)
SELECT 
    id,
    email,
    name,
    ARRAY['user']::TEXT[],
    jsonb_build_object('synced_from', 'neon_auth', 'synced_at', now()),
    now()
FROM neon_auth.users_sync
WHERE deleted_at IS NULL
ON CONFLICT (auth_user_id) DO UPDATE SET
    email = EXCLUDED.email,
    display_name = EXCLUDED.display_name,
    last_seen = now();

-- ==========================================================
-- View: Combined user info (optional convenience view)
-- ==========================================================
CREATE OR REPLACE VIEW app.users_full AS
SELECT 
    u.id,
    u.auth_user_id,
    u.email,
    u.display_name,
    u.roles,
    u.metadata,
    u.created_at,
    u.last_seen,
    n.raw_json AS neon_auth_data,
    n.created_at AS neon_created_at
FROM app.users u
LEFT JOIN neon_auth.users_sync n ON u.auth_user_id = n.id;

-- ==========================================================
-- Migration complete
-- ==========================================================
DO $$
DECLARE
    synced_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO synced_count FROM app.users WHERE metadata->>'synced_from' = 'neon_auth';
    RAISE NOTICE 'Migration 03_sync_neon_auth_users.sql completed successfully.';
    RAISE NOTICE 'Synced % users from neon_auth.users_sync', synced_count;
    RAISE NOTICE 'Created trigger: sync_neon_auth_to_app_users';
    RAISE NOTICE 'Created view: app.users_full';
END$$;
