# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import traceback
from time import time
from typing import Any

import aiohttp
import discord
import orjson
from discord import Activity, ActivityType, AllowedMentions, Intents, Status
from discord.errors import Forbidden
from discord.ext import commands
from loguru import logger

from modules import cache, maria, util
from modules.help import EmbedHelpCommand
from modules.instagram import Datalama
from modules.keychain import Keychain
from modules.redis import Redis


class MisoBot(commands.AutoShardedBot):
    def __init__(self, extensions: list[str], default_prefix: str, **kwargs: dict[str, Any]):
        super().__init__(
            help_command=EmbedHelpCommand(),
            activity=Activity(type=ActivityType.playing, name="Booting up..."),
            command_prefix=util.determine_prefix,
            case_insensitive=True,
            allowed_mentions=AllowedMentions(everyone=False),
            max_messages=20000,
            heartbeat_timeout=120,
            owner_id=133311691852218378,
            client_id=500385855072894982,
            status=Status.idle,
            chunk_guilds_at_startup=False,
            intents=Intents(  # https://discordpy.readthedocs.io/en/latest/api.html?highlight=intents#intents
                guilds=True,
                members=True,  # requires verification
                bans=True,
                emojis_and_stickers=True,
                integrations=False,
                webhooks=False,
                invites=False,
                voice_states=False,
                presences=False,  # requires verification
                guild_messages=True,
                dm_messages=True,
                guild_reactions=True,
                dm_reactions=True,
                typing=False,
                message_content=True,  # requires verification
                guild_scheduled_events=False,
                auto_moderation_configuration=False,
                auto_moderation_execution=False,
            ),
            **kwargs,
        )
        self.default_prefix = default_prefix
        self.extensions_to_load = extensions
        self.start_time = time()
        self.global_cd = commands.CooldownMapping.from_cooldown(15, 60, commands.BucketType.member)
        self.db = maria.MariaDB()
        self.cache = cache.Cache(self)
        self.keychain = Keychain()
        self.version = "5.1"
        self.extensions_loaded = False
        self.redis: Redis = Redis()
        self.datalama = Datalama(self)
        self.boot_up_time: float
        self.session: aiohttp.ClientSession
        self.register_hooks()

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=0),
            json_serialize=lambda x: orjson.dumps(x).decode(),
            timeout=aiohttp.ClientTimeout(total=30),
        )
        await self.redis.start()
        await self.db.initialize_pool()
        await self.cache.initialize_settings_cache()
        await self.load_all_extensions()
        self.boot_up_time = time() - self.start_time

    def register_hooks(self):
        """Register event hooks to the bot"""
        self.before_invoke(self.before_any_command)
        self.check(self.check_for_blacklist)
        self.check(self.cooldown_check)

    async def load_all_extensions(self):
        logger.info("Loading extensions...")
        for extension in self.extensions_to_load:
            try:
                await self.load_extension(f"cogs.{extension}")
                logger.info(f"Loaded [ {extension} ]")
            except Exception as error:
                logger.error(f"Error loading [ {extension} ]")
                traceback.print_exception(type(error), error, error.__traceback__)

        await self.load_extension("jishaku")
        self.extensions_loaded = True
        logger.info("All extensions loaded successfully!")

    async def close(self):
        """Overrides built-in close()"""
        await self.session.close()
        await self.db.cleanup()
        await super().close()

    async def on_message(self, message: discord.Message):
        """Overrides built-in on_message()"""
        await super().on_message(message)

    async def on_ready(self):
        """Overrides built-in on_ready()"""
        logger.info(f"Boot up process completed in {util.stringfromtime(self.boot_up_time)}")
        latencies = self.latencies
        logger.info(f"Loading complete | running {len(latencies)} shards")
        for shard_id, latency in latencies:
            logger.info(f"Shard [{shard_id}] - HEARTBEAT {latency}s")

    @staticmethod
    async def before_any_command(ctx: commands.Context):
        """Runs before any command"""
        if ctx.guild:
            await util.require_chunked(ctx.guild)
        ctx.timer = time()  # type: ignore
        try:
            await ctx.typing()
        except Forbidden:
            pass

    @staticmethod
    async def check_for_blacklist(ctx: commands.Context):
        """Check command invocation context for blacklist triggers"""
        return await util.is_blacklisted(ctx)

    @staticmethod
    async def cooldown_check(ctx: commands.Context):
        """Global bot cooldown to prevent spam"""
        # prevent users getting rate limited when help command does filter_commands()
        if str(ctx.invoked_with).lower() == "help":
            return True

        bucket = ctx.bot.global_cd.get_bucket(ctx.message)
        if retry_after := bucket.update_rate_limit():
            raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.member)
        return True

    @property
    def member_count(self) -> int:
        return sum(guild.member_count or 0 for guild in self.guilds)

    @property
    def guild_count(self) -> int:
        return len(self.guilds)
