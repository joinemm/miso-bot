from modules import log

logger = log.get_logger(__name__)
log.get_logger(__name__)


class Cache:
    def __init__(self, bot):
        self.bot = bot
        self.log_emoji = False
        self.prefixes = {}
        self.rolepickers = set()
        self.votechannels = set()
        self.autoresponse = {}
        self.levelupmessage = {}
        self.blacklist = {}
        self.marriages = set()
        self.starboard_settings = {}
        self.starboard_blacklisted_channels = set()
        self.event_triggers = {
            "message": 0,
            "message_delete": 0,
            "message_edit": 0,
            "reaction_add": 0,
            "reaction_remove": 0,
            "member_join": 0,
            "member_remove": 0,
            "guild_join": 0,
            "guild_remove": 0,
            "member_ban": 0,
            "member_unban": 0,
        }
        self.stats_notifications_sent = 0
        self.stats_lastfm_requests = 0
        self.stats_html_rendered = 0
        bot.loop.create_task(self.initialize_settings_cache())

    async def cache_starboard_settings(self):
        data = await self.bot.db.execute(
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
            await self.bot.db.execute(
                "SELECT channel_id FROM starboard_blacklist",
                as_list=True,
            )
        )

    async def initialize_settings_cache(self):
        self.bot.logger.info("Caching settings...")
        prefixes = await self.bot.db.execute("SELECT guild_id, prefix FROM guild_prefix")
        for guild_id, prefix in prefixes:
            self.prefixes[str(guild_id)] = prefix

        self.rolepickers = set(
            await self.bot.db.execute("SELECT channel_id FROM rolepicker_settings", as_list=True)
        )

        self.votechannels = set(
            await self.bot.db.execute("SELECT channel_id FROM voting_channel", as_list=True)
        )

        guild_settings = await self.bot.db.execute(
            "SELECT guild_id, levelup_messages, autoresponses FROM guild_settings"
        )
        for guild_id, levelup_messages, autoresponses in guild_settings:
            self.autoresponse[str(guild_id)] = autoresponses
            self.levelupmessage[str(guild_id)] = levelup_messages

        self.blacklist = {
            "global": {
                "user": set(
                    await self.bot.db.execute("SELECT user_id FROM blacklisted_user", as_list=True)
                ),
                "guild": set(
                    await self.bot.db.execute(
                        "SELECT guild_id FROM blacklisted_guild", as_list=True
                    )
                ),
                "channel": set(
                    await self.bot.db.execute(
                        "SELECT channel_id FROM blacklisted_channel", as_list=True
                    )
                ),
            }
        }

        self.marriages = [
            set(pair)
            for pair in await self.bot.db.execute(
                "SELECT first_user_id, second_user_id FROM marriage"
            )
        ]

        for guild_id, user_id in await self.bot.db.execute(
            "SELECT guild_id, user_id FROM blacklisted_member"
        ):
            try:
                self.blacklist[str(guild_id)]["member"].add(user_id)
            except KeyError:
                self.blacklist[str(guild_id)] = {"member": {user_id}, "command": set()}

        for guild_id, command_name in await self.bot.db.execute(
            "SELECT guild_id, command_name FROM blacklisted_command"
        ):
            try:
                self.blacklist[str(guild_id)]["command"].add(command_name.lower())
            except KeyError:
                self.blacklist[str(guild_id)] = {
                    "member": set(),
                    "command": {command_name.lower()},
                }

        await self.cache_starboard_settings()
