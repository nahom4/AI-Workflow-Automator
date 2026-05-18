import asyncio, sys, time
sys.path.insert(0, ".")
from worker import db

async def run():
    client = db.get_client()
    now = int(time.time() * 1000)
    print(f"Current time (ms): {now}")

    rs = await client.execute("SELECT id, name, status, next_run_at FROM automations")
    print(f"\nAll automations ({len(rs.rows)}):")
    for row in rs.rows:
        d = dict(zip(rs.columns, row))
        diff = now - d["next_run_at"]
        print(f"  {d['name'][:40]} | status={d['status']} | next_run_at={d['next_run_at']} | diff={diff}ms")

asyncio.run(run())
