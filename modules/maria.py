import aiomysql
import asyncio
import os
from modules import log, exceptions


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
        else:
            return True

    async def initialize_pool(self):
        cred = {
            "db": os.environ.get("MISOBOT_DB_NAME"),
            "host": "localhost",
            "port": 3306,
            "user": os.environ.get("MISOBOT_DB_USER"),
            "password": os.environ.get("MISOBOT_DB_PASSWORD"),
        }
        logger.info(
            f"Connecting to database {cred['db']} on {cred['host']}:{cred['port']} as {cred['user']}"
        )
        self.pool = await aiomysql.create_pool(**cred, echo=False)
        logger.info("Initialized MariaDB connection pool")

    async def cleanup(self):
        self.pool.close()
        await self.pool.wait_closed()
        logger.info("Closed MariaDB connection pool")

    async def execute(self, statement, *params, one_row=False, one_value=False, as_list=False):
        if await self.wait_for_pool():
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(statement, params)
                    await conn.commit()
                    data = await cur.fetchall()
            if data is None:
                return ()
            else:
                if data:
                    if one_value:
                        return data[0][0]
                    elif one_row:
                        return data[0]
                    elif as_list:
                        return [row[0] for row in data]
                    else:
                        return data
                else:
                    return ()
        else:
            raise exceptions.Error("Could not connect to the local MariaDB instance!")

    async def executemany(self, statement, params):
        if await self.wait_for_pool():
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(statement, params)
                    await conn.commit()
            return ()
        else:
            raise exceptions.Error("Could not connect to the local MariaDB instance!")
