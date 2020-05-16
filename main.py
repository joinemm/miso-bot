import os
import sys
import discord
import traceback
from discord.ext import commands
from time import time
from helpers import log
from helpers import utilityfunctions as util
from data import database as db

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()

if len(sys.argv) > 1:
    DEV = sys.argv[1] == 'dev'
else:
    DEV = False

logger.info(f"Developer mode is {'ON' if DEV else 'OFF'}")

TOKEN = os.environ['MISO_BOT_TOKEN_BETA' if DEV else 'MISO_BOT_TOKEN']
bot = commands.AutoShardedBot(
    command_prefix=util.determine_prefix,
    case_insensitive=True
)

bot.default_prefix = '<' if DEV else '>'

extensions = [
    'events',
    'config',
    'errorhandler',
    'customcommands',
    'fishy',
    'info',
    'rolepicker',
    'mod',
    'owner',
    'notifications',
    'miscellaneous',
    'media',
    'lastfm',
    'user',
    'images',
    'utility',
    'wordcloud',
    'typings',
    'reminders',
    'bangs',
]


@bot.event
async def on_ready():
    # cache owner from appinfo
    bot.owner = (await bot.application_info()).owner
    bot.start_time = time()
    latencies = bot.latencies
    logger.info(f"Loading complete | running {len(latencies)} shards")
    for shard_id, latency in latencies:
        logger.info(f"Shard [{shard_id}] - HEARTBEAT {latency}s")


@bot.before_invoke
async def before_any_command(ctx):
    ctx.timer = time()
    try:
        await ctx.trigger_typing()
    except discord.errors.Forbidden:
        pass


@bot.check
async def check_for_blacklist(ctx):
    if ctx.guild is None:
        raise commands.NoPrivateMessage
    else:
        return db.is_blacklisted(ctx)


@bot.event
async def on_command_completion(ctx):
    # prevent double invocation for subcommands
    if ctx.invoked_subcommand is None:
        command_logger.info(log.log_command(ctx))
        db.log_command_usage(ctx)


if __name__ == "__main__":
    for extension in extensions:
        try:
            bot.load_extension(f"cogs.{extension}")
            logger.info(f"Loaded [ {extension} ]")
        except Exception as error:
            logger.error(f"Error loading [ {extension} ]")
            traceback.print_exception(type(error), error, error.__traceback__)
            
    bot.run(TOKEN)
