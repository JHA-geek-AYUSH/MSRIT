import asyncio
import asyncpg

async def check():
    try:
        conn = await asyncpg.connect(
            'postgresql://gemmaFin:gemmaFin123@localhost:5432/gemmaFin_db', timeout=5
        )
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
        names = [r['tablename'] for r in tables]
        print('DB connected. Tables:', sorted(names))
        await conn.close()
    except Exception as e:
        print('DB error:', e)

asyncio.run(check())
