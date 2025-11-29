#!/usr/bin/env python3
"""
Test script to validate Neon PostgreSQL connection and user upsert.

Usage:
    cd backend
    uv run python scripts/test_neon_connection.py

Prerequisites:
    - NEON_DATABASE_URL must be set in .env or environment
    - The migration infra/01_create_app_schema.sql must have been run
    - asyncpg must be installed (part of requirements.txt)

What this script does:
    1. Loads NEON_DATABASE_URL from environment
    2. Connects using asyncpg
    3. Prints count(*) from app.users
    4. Runs upsert_user() with test values
    5. Prints the inserted/updated row
    6. Cleans up test data (optional)
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed, using environment variables only")


async def test_neon_connection():
    """Test Neon PostgreSQL connection and user operations."""
    
    # Get database URL
    database_url = os.getenv("NEON_DATABASE_URL")
    if not database_url:
        print("❌ ERROR: NEON_DATABASE_URL not set in environment")
        print("   Please set it in .env or export it before running this script")
        sys.exit(1)
    
    # Mask password in output
    masked_url = database_url
    if "@" in database_url:
        parts = database_url.split("@")
        masked_url = parts[0].rsplit(":", 1)[0] + ":****@" + parts[1]
    print(f"📡 Connecting to: {masked_url}")
    
    try:
        import asyncpg
    except ImportError:
        print("❌ ERROR: asyncpg not installed")
        print("   Run: uv add asyncpg")
        sys.exit(1)
    
    try:
        # Connect to database
        conn = await asyncpg.connect(
            database_url,
            ssl="require",
            timeout=30,
        )
        print("✅ Connected to Neon PostgreSQL")
        
        # Check if app schema exists
        schema_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'app')"
        )
        if not schema_exists:
            print("❌ ERROR: 'app' schema does not exist")
            print("   Run the migration first:")
            print("   psql $NEON_DATABASE_URL -f infra/01_create_app_schema.sql")
            await conn.close()
            sys.exit(1)
        print("✅ Schema 'app' exists")
        
        # Check if users table exists
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'app' AND table_name = 'users'
            )
            """
        )
        if not table_exists:
            print("❌ ERROR: 'app.users' table does not exist")
            print("   Run the migration first")
            await conn.close()
            sys.exit(1)
        print("✅ Table 'app.users' exists")
        
        # Count users
        count = await conn.fetchval("SELECT COUNT(*) FROM app.users")
        print(f"📊 Current user count: {count}")
        
        # Test upsert_user function
        print("\n🔄 Testing upsert_user...")
        
        # Import and test our db module - must init pool first!
        from app.db import upsert_user, init_pg_pool, close_pg_pool
        
        await init_pg_pool()  # Initialize the connection pool
        
        test_user = await upsert_user(
            auth_user_id="test_auth_user_12345",
            email="test@example.com",
            display_name="Test User",
            roles=["analyst"],
            metadata={"department": "Security", "test": True},
        )
        
        if test_user:
            print("✅ upsert_user() succeeded!")
            print(f"   ID: {test_user.get('id')}")
            print(f"   Auth User ID: {test_user.get('auth_user_id')}")
            print(f"   Email: {test_user.get('email')}")
            print(f"   Display Name: {test_user.get('display_name')}")
            print(f"   Roles: {test_user.get('roles')}")
            print(f"   Metadata: {test_user.get('metadata')}")
            print(f"   Created At: {test_user.get('created_at')}")
            print(f"   Last Seen: {test_user.get('last_seen')}")
        else:
            print("❌ upsert_user() returned None")
        
        # Verify by querying directly
        row = await conn.fetchrow(
            "SELECT * FROM app.users WHERE auth_user_id = $1",
            "test_auth_user_12345"
        )
        if row:
            print("\n📝 Direct query verification:")
            print(f"   Row found: ID={row['id']}, email={row['email']}")
        
        # Count after insert
        count_after = await conn.fetchval("SELECT COUNT(*) FROM app.users")
        print(f"\n📊 User count after upsert: {count_after}")
        
        # Optional: Clean up test data
        cleanup = os.getenv("CLEANUP_TEST_DATA", "false").lower() == "true"
        if cleanup:
            await conn.execute(
                "DELETE FROM app.users WHERE auth_user_id = $1",
                "test_auth_user_12345"
            )
            print("🧹 Cleaned up test user")
        
        # Test other tables exist
        print("\n📋 Checking other tables...")
        for table in ["incidents", "runbooks", "telemetry", "sessions"]:
            exists = await conn.fetchval(
                f"""
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'app' AND table_name = '{table}'
                )
                """
            )
            status = "✅" if exists else "❌"
            print(f"   {status} app.{table}")
        
        # Check vector extension
        vector_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        if vector_exists:
            print("\n✅ pgvector extension is enabled")
        else:
            print("\n⚠️ pgvector extension not found (RAG features may be limited)")
        
        await conn.close()
        print("\n🎉 All connection tests passed!")
        return True
        
    except asyncpg.exceptions.InvalidPasswordError:
        print("❌ ERROR: Invalid password in connection string")
        sys.exit(1)
    except asyncpg.exceptions.InvalidCatalogNameError as e:
        print(f"❌ ERROR: Database not found: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        sys.exit(1)


async def test_from_db_module():
    """Test using the db module's connection pool."""
    print("\n" + "="*60)
    print("Testing db module connection pool...")
    print("="*60)
    
    from app.db import init_pg_pool, close_pg_pool, get_user_by_auth_id
    
    # Initialize pool
    pool = await init_pg_pool()
    if pool:
        print("✅ Connection pool initialized")
        
        # Test get_user_by_auth_id
        user = await get_user_by_auth_id("test_auth_user_12345")
        if user:
            print(f"✅ Found test user: {user.get('email')}")
        else:
            print("ℹ️ Test user not found (expected if cleaned up)")
        
        # Close pool
        await close_pg_pool()
        print("✅ Connection pool closed")
    else:
        print("⚠️ Connection pool not initialized (using in-memory mode)")


if __name__ == "__main__":
    print("="*60)
    print("Neon PostgreSQL Connection Test")
    print("="*60)
    print()
    
    # Run tests
    asyncio.run(test_neon_connection())
    asyncio.run(test_from_db_module())
