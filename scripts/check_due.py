import asyncio, sys, os
sys.path.insert(0, ".")
from worker import db

async def run():
    await db.ensure_schema()
    rows = await db.fetch_due_automations()
    print(f"Due automations: {len(rows)}")
    for r in rows:
        print(f"  - {r['name']} | status={r['status']} | next_run_at={r['next_run_at']}")

asyncio.run(run())
