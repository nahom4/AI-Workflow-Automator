import asyncio, sys
sys.path.insert(0, ".")
from worker import db

async def run():
    client = db.get_client()
    rs = await client.execute(
        "SELECT automation_id, title, score, source_domain FROM leads ORDER BY score DESC LIMIT 10"
    )
    print(f"Leads: {len(rs.rows)}")
    for row in rs.rows:
        d = dict(zip(rs.columns, row))
        print(f"  [{d['score']:.1f}] {d['title'][:60]} ({d['source_domain']})")

asyncio.run(run())
