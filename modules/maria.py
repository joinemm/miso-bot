import asyncio
import os
from dataclasses import dataclass
from typing import Optional, Union

import aiomysql
from aiomysql import Connection, Cursor, Pool

from modules import exceptions, log

logger = log.get_logger(__name__)
log.get_logger("aiomysql")


@dataclass()
class DatabaseCredentials:
    db: str
    host: str
    port: int
    user: str
    password: str

    def __str__(self) -> str:
        return f"{self.db} on {self.host}:{self.port} as {self.user}"

    def spread(self) -> tuple:
        return (self.db, self.host, self.port, self.user, self.password)


class MariaDB:
    MAX_CONNECTION_RETRY = 10
    CONNECTION_RETRY_WAIT = 1

    def __init__(self):
        self.pool: Optional[Pool] = None

    async def wait_for_pool(self):
        retries = 0
        while self.pool is None and retries < self.MAX_CONNECTION_RETRY:
            logger.warning("Pool not initialized yet. waiting...")
            await asyncio.sleep(self.CONNECTION_RETRY_WAIT)
            retries += 1

        if self.pool is None:
            logger.error("Pool wait timeout! ABORTING")
            return False

        return True

    async def initialize_pool(self):
        creds = DatabaseCredentials(
            os.environ["DB_NAME"],
            os.environ["DB_HOST"],
            int(os.environ["DB_PORT"]),
            os.environ["DB_USER"],
            os.environ["DB_PASSWORD"],
        )
        logger.info(f"Connecting to database {creds}")
        maxsize = int(os.environ.get("DB_POOL_SIZE", 10))
        self.pool = await aiomysql.create_pool(
            **creds.__dict__,
            maxsize=maxsize,
            autocommit=True,
            echo=False,
        )
        logger.info(f"Initialized MariaDB connection pool with {maxsize} connections")

    async def cleanup(self):
        """Close the pool gracefully before exit"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Closed MariaDB connection pool")

    async def _execute(self, sql: str, params, return_data=False) -> Union[list, int]:
        """Internal executor, handles connection logic and returns data or changed rows"""
        if await self.wait_for_pool() and self.pool:
            conn: Connection
            async with self.pool.acquire() as conn:
                cur: Cursor
                async with conn.cursor() as cur:
                    changed: int = await cur.execute(sql, params)
                    if return_data:
                        return await cur.fetchall()
                    else:
                        return changed
        raise exceptions.CommandError("Could not connect to the local MariaDB instance!")

    async def execute(self, statement: str, *params) -> int:
        """Executes sql and returns the number of rows affected"""
        changes = await self._execute(statement, params)
        if isinstance(changes, int):
            return changes
        else:
            return 0

    async def fetch(self, statement: str, *params):
        """Fetch data"""
        data = await self._execute(statement, params, return_data=True)
        if data and not isinstance(data, int):
            return data
        return None

    async def fetch_value(self, statement: str, *params):
        """Fetches the first value of the first row of the query"""
        data = await self._execute(statement, params, return_data=True)
        if data and not isinstance(data, int):
            return data[0][0]
        return None

    async def fetch_row(self, statement: str, *params) -> list:
        """Fetches the first row of the query"""
        data = await self._execute(statement, params, return_data=True)
        if data and not isinstance(data, int):
            return data[0]
        return []

    async def fetch_flattened(self, statement: str, *params) -> list:
        """Fetches the first element of every row as a flattened list"""
        data = await self._execute(statement, params, return_data=True)
        if data and not isinstance(data, int):
            return [row[0] for row in data]
        return []

    async def executemany(self, statement: str, params: list[tuple]):
        """Execute the same sql with different arguments"""
        if await self.wait_for_pool() and self.pool:
            conn: Connection
            async with self.pool.acquire() as conn:
                cur: Cursor
                async with conn.cursor() as cur:
                    await cur.executemany(statement, params)
        raise exceptions.CommandError("Could not connect to the local MariaDB instance!")
