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
from data import database as db

uvloop.install()

logger = log.get_logger(__name__)

if len(sys.argv) > 1:
    DEV = sys.argv[1] == "dev"
else:
    DEV = False

logger.info(f"Developer mode is {'ON' if DEV else 'OFF'}")

TOKEN = os.environ["MISO_BOT_TOKEN_BETA" if DEV else "MISO_BOT_TOKEN"]
bot = commands.AutoShardedBot(
    help_command=help.EmbedHelpCommand(),
    command_prefix=util.determine_prefix,
    case_insensitive=True,
    allowed_mentions=discord.AllowedMentions(everyone=False),
)

bot.default_prefix = "<" if DEV else ">"

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
    "wordcloud",
    "typings",
    "reminders",
    "bangs",
    "opgg",
    "webserver",
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
    return db.is_blacklisted(ctx)


if __name__ == "__main__":
    for extension in extensions:
        try:
            bot.load_extension(f"cogs.{extension}")
            logger.info(f"Loaded [ {extension} ]")
        except Exception as error:
            logger.error(f"Error loading [ {extension} ]")
            traceback.print_exception(type(error), error, error.__traceback__)

    bot.start_time = time()
    bot.run(TOKEN)
