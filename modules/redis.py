# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import os

import redis.asyncio as redis


class Redis:
    def __init__(self) -> None:
        self.url = os.environ.get("REDIS_URL")
        self.enabled = self.url is not None
        self.pool: redis.Redis

    async def start(self):
        if self.enabled:
            self.pool = await redis.from_url(self.url)

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
