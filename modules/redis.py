import aioredis


class Redis:
    def __init__(self) -> None:
        self.pool: aioredis.Redis

    async def start(self):
        self.pool = await aioredis.from_url(
            "redis://redis", encoding="utf-8", decode_responses=True
        )

    async def set(self, key, value, expiry: int | None = None):
        await self.pool.set(key, value, ex=expiry)

    async def get(self, key):
        val = await self.pool.get(key)
        return val

    async def close(self):
        await self.pool.close()
