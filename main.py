import os
import sys
import uvloop
import discord
import traceback
from discord.ext import commands
from time import time
from helpers import log
from helpers import help
from helpers import utilityfunctions as util
from dotenv import load_dotenv
from modules import maria, queries

load_dotenv(verbose=True)
uvloop.install()

logger = log.get_logger(__name__)

if len(sys.argv) > 1:
    DEV = sys.argv[1] == "dev"
else:
    DEV = False

logger.info(f"Developer mode is {'ON' if DEV else 'OFF'}")

TOKEN = os.environ["MISO_BOT_TOKEN_BETA" if DEV else "MISO_BOT_TOKEN"]


class MisoBot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.default_prefix = ("<" if DEV else ">",)
        self.logger = logger
        self.start_time = time()
        self.global_cd = commands.CooldownMapping.from_cooldown(15, 60, commands.BucketType.member)
        self.db = maria.MariaDB(self)

    async def close(self):
        await self.db.cleanup()
        await super().close()

    async def on_message(self, message):
        if not bot.is_ready:
            return

        await super().on_message(message)


bot = MisoBot(
    owner_id=133311691852218378,
    help_command=help.EmbedHelpCommand(),
    command_prefix=util.determine_prefix,
    case_insensitive=True,
    allowed_mentions=discord.AllowedMentions(everyone=False),
    intents=discord.Intents.all(),
)

extensions = [
    "events",
    "config",
    "errorhandler",
    "customcommands",
    "fishy",
    "info",
    "rolepicker",
    "mod",
    "owner",
    "notifications",
    "miscellaneous",
    "media",
    "lastfm",
    "user",
    "images",
    "utility",
    "typings",
    "reminders",
    "bangs",
    "opgg",
    "webserver",
    "reddit",
]


@bot.before_invoke
async def before_any_command(ctx):
    """Runs before any command"""
    ctx.timer = time()
    try:
        await ctx.trigger_typing()
    except discord.errors.Forbidden:
        pass


@bot.check
async def check_for_blacklist(ctx):
    """Check command invocation context for blacklist triggers"""
    return await queries.is_blacklisted(ctx)


@bot.check
async def cooldown_check(ctx):
    """Global bot cooldown to prevent spam"""
    # prevent users getting rate limited when help command does filter_commands()
    if str(ctx.invoked_with).lower() == "help":
        return True

    bucket = ctx.bot.global_cd.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        raise commands.CommandOnCooldown(bucket, retry_after)
    return True


if __name__ == "__main__":
    for extension in extensions:
        try:
            bot.load_extension(f"cogs.{extension}")
            logger.info(f"Loaded [ {extension} ]")
        except Exception as error:
            logger.error(f"Error loading [ {extension} ]")
            traceback.print_exception(type(error), error, error.__traceback__)

    bot.load_extension("jishaku")
    bot.start_time = time()
    bot.run(TOKEN)
