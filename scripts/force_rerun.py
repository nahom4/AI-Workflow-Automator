"""Force all automations to be due right now and clean up stuck runs."""
import asyncio, sys, time
sys.path.insert(0, ".")
from worker import db

async def run():
    client = db.get_client()
    now = int(time.time() * 1000)

    # Clean up runs stuck in "running" status
    rs = await client.execute("UPDATE runs SET status='error', finished_at=? WHERE status='running'", [now])
    print(f"Cleaned up stuck runs: {rs.rows_affected}")

    # Reset all automations to be due now
    rs2 = await client.execute(
        "UPDATE automations SET status='active', next_run_at=? WHERE status IN ('active','broken')",
        [now]
    )
    print(f"Reset automations: {rs2.rows_affected}")

    rs3 = await client.execute("SELECT name, status, next_run_at FROM automations")
    for row in rs3.rows:
        print(dict(zip(rs3.columns, row)))

asyncio.run(run())
