import asyncio
import os

import aiomysql

from modules import exceptions, log

logger = log.get_logger(__name__)
log.get_logger("aiomysql")


class MariaDB:
    def __init__(self, bot):
        self.bot = bot
        self.pool = None
        bot.loop.create_task(self.initialize_pool())

    async def wait_for_pool(self):
        i = 0
        while self.pool is None and i < 10:
            logger.warning("Pool not initialized yet. waiting...")
            await asyncio.sleep(1)
            i += 1

        if self.pool is None:
            logger.error("Pool wait timeout! ABORTING")
            return False
        return True

    async def initialize_pool(self):
        cred = {
            "db": os.environ["DB_NAME"],
            "host": os.environ["DB_HOST"],
            "port": int(os.environ["DB_PORT"]),
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
        }
        logger.info(
            f"Connecting to database {cred['db']} on {cred['host']}:{cred['port']} as {cred['user']}"
        )
        maxsize = int(os.environ.get("DB_POOL_SIZE", 10))
        self.pool = await aiomysql.create_pool(
            **cred, maxsize=maxsize, autocommit=True, echo=False
        )
        logger.info(f"Initialized MariaDB connection pool with {maxsize} connections")

    async def cleanup(self):
        self.pool.close()
        await self.pool.wait_closed()
        logger.info("Closed MariaDB connection pool")

    async def execute(self, statement, *params, one_row=False, one_value=False, as_list=False):
        if await self.wait_for_pool():
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(statement, params)
                    data = await cur.fetchall()
            if data is None:
                return ()
            if data:
                if one_value:
                    return data[0][0]
                if one_row:
                    return data[0]
                if as_list:
                    return [row[0] for row in data]
                return data
            return ()
        raise exceptions.CommandError("Could not connect to the local MariaDB instance!")

    async def executemany(self, statement, params):
        if await self.wait_for_pool():
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(statement, params)
                    await conn.commit()
            return ()
        raise exceptions.CommandError("Could not connect to the local MariaDB instance!")
