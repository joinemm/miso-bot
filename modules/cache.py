from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from modules.misobot import MisoBot


class Cache:
    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.log_emoji = False
        self.prefixes = {}
        self.rolepickers = set()
        self.votechannels = set()
        self.autoresponse = {}
        self.blacklist = {}
        self.logging_settings = {}
        self.autoroles = {}
        self.marriages = []
        self.starboard_settings = {}
        self.starboard_blacklisted_channels = set()

    async def cache_starboard_settings(self):
        data = await self.bot.db.fetch(
            """
            SELECT guild_id, is_enabled, channel_id, reaction_count,
                emoji_name, emoji_id, emoji_type, log_channel_id
            FROM starboard_settings
            """
        )
        if not data:
            return
        for (
            guild_id,
            is_enabled,
            channel_id,
            reaction_count,
            emoji_name,
            emoji_id,
            emoji_type,
            log_channel_id,
        ) in data:
            self.starboard_settings[str(guild_id)] = [
                is_enabled,
                channel_id,
                reaction_count,
                emoji_name,
                emoji_id,
                emoji_type,
                log_channel_id,
            ]

        self.starboard_blacklisted_channels = set(
            await self.bot.db.fetch_flattened(
                "SELECT channel_id FROM starboard_blacklist",
            )
        )

    async def cache_logging_settings(self):
        logging_settings = await self.bot.db.fetch(
            """
            SELECT guild_id, member_log_channel_id, ban_log_channel_id, message_log_channel_id
            FROM logging_settings
            """
        )
        if logging_settings:
            for (
                guild_id,
                member_log_channel_id,
                ban_log_channel_id,
                message_log_channel_id,
            ) in logging_settings:
                self.logging_settings[str(guild_id)] = {
                    "member_log_channel_id": member_log_channel_id,
                    "ban_log_channel_id": ban_log_channel_id,
                    "message_log_channel_id": message_log_channel_id,
                }

    async def cache_autoroles(self):
        data = await self.bot.db.fetch("SELECT guild_id, role_id FROM autorole")
        if data:
            for guild_id, role_id in data:
                try:
                    self.autoroles[str(guild_id)].add(role_id)
                except KeyError:
                    self.autoroles[str(guild_id)] = {role_id}

    async def initialize_settings_cache(self):
        logger.info("Caching settings...")
        prefixes = await self.bot.db.fetch("SELECT guild_id, prefix FROM guild_prefix")
        if prefixes:
            for guild_id, prefix in prefixes:
                self.prefixes[str(guild_id)] = prefix

        self.rolepickers = set(
            await self.bot.db.fetch_flattened("SELECT channel_id FROM rolepicker_settings")
        )

        self.votechannels = set(
            await self.bot.db.fetch_flattened("SELECT channel_id FROM voting_channel")
        )

        guild_settings = await self.bot.db.fetch(
            "SELECT guild_id, autoresponses FROM guild_settings"
        )
        if guild_settings:
            for guild_id, autoresponses in guild_settings:
                self.autoresponse[str(guild_id)] = autoresponses

        self.blacklist = {
            "global": {
                "user": set(
                    await self.bot.db.fetch_flattened("SELECT user_id FROM blacklisted_user")
                ),
                "guild": set(
                    await self.bot.db.fetch_flattened("SELECT guild_id FROM blacklisted_guild")
                ),
                "channel": set(
                    await self.bot.db.fetch_flattened("SELECT channel_id FROM blacklisted_channel")
                ),
            }
        }

        pairs = await self.bot.db.fetch("SELECT first_user_id, second_user_id FROM marriage")
        self.marriages = [set(pair) for pair in pairs] if pairs else []

        blacklisted_members = await self.bot.db.fetch(
            "SELECT guild_id, user_id FROM blacklisted_member"
        )
        if blacklisted_members:
            for guild_id, user_id in blacklisted_members:
                try:
                    self.blacklist[str(guild_id)]["member"].add(user_id)
                except KeyError:
                    self.blacklist[str(guild_id)] = {"member": {user_id}, "command": set()}
        blacklisted_commands = await self.bot.db.fetch(
            "SELECT guild_id, command_name FROM blacklisted_command"
        )
        if blacklisted_commands:
            for guild_id, command_name in blacklisted_commands:
                try:
                    self.blacklist[str(guild_id)]["command"].add(command_name.lower())
                except KeyError:
                    self.blacklist[str(guild_id)] = {
                        "member": set(),
                        "command": {command_name.lower()},
                    }

        await self.cache_starboard_settings()
        await self.cache_logging_settings()
        await self.cache_autoroles()
