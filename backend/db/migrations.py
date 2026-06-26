import os
from backend.db.pool import get_pool

async def run_migrations():
    pool = get_pool()
    schema_path = os.path.join(os.path.dirname(__file__), "..", "..", "infra", "init", "001_schema.sql")
    
    # Read the schema file
    try:
        with open(schema_path, "r") as f:
            schema_sql = f.read()
    except Exception as e:
        print(f"Error reading schema file: {e}")
        return

    # In a real app we'd use Alembic or similar, but for now we'll just check if the documents table exists
    async with pool.acquire() as conn:
        try:
            # Check if applied
            val = await conn.fetchval("SELECT to_regclass('public.documents')")
            if not val:
                print("Applying 001_schema.sql")
                await conn.execute(schema_sql)
            else:
                print("Schema already applied.")
        except Exception as e:
            print(f"Migration error: {e}")
