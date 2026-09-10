#!/usr/bin/env python
"""
إنشاء جداول AI Sales Agent في قاعدة البيانات.
يُستدعى من startCommand في render.yaml قبل uvicorn.
"""

import asyncio
import os
import sys
from pathlib import Path

# ─── أضف جذر المشروع إلى sys.path ───
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


# ═══════════════════════════════════════════════════════════════════
# قراءة DATABASE_URL
# ═══════════════════════════════════════════════════════════════════

def get_url() -> str:
    url = os.getenv("DATABASE_URL")

    if not url:
        print("❌ DATABASE_URL is not set")
        sys.exit(1)

    # إصلاح البروتوكول
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


# ═══════════════════════════════════════════════════════════════════
# SQL Statements
# ═══════════════════════════════════════════════════════════════════

SQL_STATEMENTS = [
    # 1) enum
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lead_stage') THEN
            CREATE TYPE lead_stage AS ENUM (
                'NEW','QUALIFYING','QUALIFIED','CONTACT_REQUESTED',
                'READY_TO_BUY','HANDED_OFF','LOST'
            );
        END IF;
    END $$;
    """,

    # 2) visitors
    """
    CREATE TABLE IF NOT EXISTS visitors (
        id SERIAL PRIMARY KEY,
        visitor_uid VARCHAR(64) NOT NULL,
        first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        user_agent VARCHAR(255),
        ip_hash VARCHAR(64),
        locale VARCHAR(16),
        referrer VARCHAR(500)
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ix_visitors_visitor_uid
        ON visitors (visitor_uid);
    """,

    # 3) leads
    """
    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        visitor_id INTEGER NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
        stage lead_stage NOT NULL DEFAULT 'NEW',
        score INTEGER NOT NULL DEFAULT 0,
        name VARCHAR(120),
        company VARCHAR(120),
        contact VARCHAR(255),
        project_type VARCHAR(120),
        problem TEXT,
        desired_solution TEXT,
        budget VARCHAR(120),
        timeline VARCHAR(120),
        intent VARCHAR(100),
        next_action VARCHAR(100),
        summary TEXT,
        handoff_reason TEXT,
        handoff_at TIMESTAMPTZ,
        notified_owner INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_leads_visitor_id ON leads (visitor_id);",
    "CREATE INDEX IF NOT EXISTS ix_leads_stage ON leads (stage);",
    "CREATE INDEX IF NOT EXISTS ix_leads_score ON leads (score);",

    # 4) messages
    """
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        role VARCHAR(16) NOT NULL,
        content TEXT,
        tool_name VARCHAR(64),
        tool_payload TEXT,
        tool_result TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_messages_lead_id ON messages (lead_id);",
    "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages (created_at);",
]


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

async def main() -> int:
    print("═══════════════════════════════════════════════")
    print(" 🔧 init_db: ensuring chat tables exist")
    print("═══════════════════════════════════════════════")

    url = get_url()
    print(f"→ DB host: {url.split('@')[-1].split('/')[0]}")

    engine = create_async_engine(url, echo=False)

    try:
        async with engine.begin() as conn:
            for i, stmt in enumerate(SQL_STATEMENTS, 1):
                print(f"  [{i}/{len(SQL_STATEMENTS)}] executing…")
                await conn.execute(text(stmt))

        # تحقق
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname='public'
                  AND tablename IN ('visitors','leads','messages')
                ORDER BY tablename
            """))
            tables = sorted([r[0] for r in result.fetchall()])

        print(f"✅ Tables: {tables}")

        expected = {"visitors", "leads", "messages"}
        if set(tables) == expected:
            print("🎉 All chat tables ready.")
            return 0
        else:
            print(f"⚠️  Missing: {expected - set(tables)}")
            return 1

    except Exception as e:
        print(f"❌ init_db failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
