import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

import aiomysql
from aiomysql import Connection, Cursor, Pool
from loguru import logger

from modules import exceptions


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

    async def run_sql(self, sql: str, params: Optional[tuple] = None) -> tuple[int, Any]:
        """Internal executor, handles connection logic and returns data or changed rows"""
        if await self.wait_for_pool() and self.pool:
            conn: Connection
            async with self.pool.acquire() as conn:
                cur: Cursor
                async with conn.cursor() as cur:
                    changed: int = await cur.execute(sql, params)
                    return changed, await cur.fetchall()
        raise exceptions.CommandError("Could not connect to the local MariaDB instance!")

    async def execute(self, statement: str, *params) -> int:
        """Executes sql and returns the number of rows affected"""
        changes, _ = await self.run_sql(statement, params)
        return changes

    async def fetch(self, statement: str, *params):
        """Fetch data"""
        _, data = await self.run_sql(statement, params)
        return data or None

    async def fetch_value(self, statement: str, *params):
        """Fetches the first value of the first row of the query"""
        _, data = await self.run_sql(statement, params)
        return data[0][0] if data else None

    async def fetch_row(self, statement: str, *params) -> list:
        """Fetches the first row of the query"""
        _, data = await self.run_sql(statement, params)
        return data[0] if data else []

    async def fetch_flattened(self, statement: str, *params) -> list:
        """Fetches the first element of every row as a flattened list"""
        _, data = await self.run_sql(statement, params)
        return [row[0] for row in data] if data else []

    async def executemany(self, statement: str, params: list[tuple]):
        """Execute the same sql with different arguments"""
        if await self.wait_for_pool() and self.pool:
            conn: Connection
            async with self.pool.acquire() as conn:
                cur: Cursor
                async with conn.cursor() as cur:
                    await cur.executemany(statement, params)
        raise exceptions.CommandError("Could not connect to the local MariaDB instance!")
