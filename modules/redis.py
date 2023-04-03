import os

import aioredis


class Redis:
    def __init__(self) -> None:
        self.enabled = os.environ.get("USE_REDIS_CACHE") == "1"
        self.pool: aioredis.Redis

    async def start(self):
        if self.enabled:
            self.pool = await aioredis.from_url(
                "redis://redis", encoding="utf-8", decode_responses=True
            )

    async def set(self, key, value, expiry: int | None = None):
        if not self.enabled:
            return

        await self.pool.set(key, value, ex=expiry)

    async def get(self, key):
        if not self.enabled:
            return None

        return await self.pool.get(key)

    async def close(self):
        if self.enabled:
            await self.pool.close()
