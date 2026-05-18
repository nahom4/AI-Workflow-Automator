import asyncio, sys, time
sys.path.insert(0, ".")
from worker import db

async def run():
    client = db.get_client()
    now = int(time.time() * 1000)
    await client.execute(
        "UPDATE automations SET status='active', next_run_at=? WHERE status='broken'",
        [now]
    )
    rs = await client.execute("SELECT name, status, next_run_at FROM automations")
    for row in rs.rows:
        print(dict(zip(rs.columns, row)))

asyncio.run(run())
