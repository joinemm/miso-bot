from modules import log


logger = log.get_logger(__name__)
log.get_logger(__name__)


class Cache:
    def __init__(self, bot):
        self.bot = bot
        self.prefixes = {}
        self.rolepickers = set()
        self.votechannels = set()
        self.autoresponse = {}
        self.levelupmessage = {}
        bot.loop.create_task(self.initialize_settings_cache())

    async def initialize_settings_cache(self):
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
