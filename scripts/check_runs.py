import asyncio, sys
sys.path.insert(0, ".")
from worker import db

async def run():
    client = db.get_client()
    rs = await client.execute(
        "SELECT r.id, r.automation_id, r.status, r.errors_json, rl.level, rl.message "
        "FROM runs r LEFT JOIN run_logs rl ON rl.run_id = r.id "
        "ORDER BY r.started_at DESC LIMIT 30"
    )
    for row in rs.rows:
        d = dict(zip(rs.columns, row))
        print(f"[{d['level'] or 'run'}] {d['status']} | {d['message'] or d['errors_json']}")

asyncio.run(run())
