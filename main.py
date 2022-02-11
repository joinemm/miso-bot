import logging
import os
import sys
import traceback
from time import time

import nextcord
import uvloop
from nextcord.ext import commands

from modules import cache, log, maria, util
from modules.help import EmbedHelpCommand

# from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO)

uvloop.install()
# load_dotenv(verbose=True)
logger = log.get_logger(__name__)

DEV = "dev" in sys.argv
maintainance_mode = "maintainance" in sys.argv

if DEV:
    logger.info("Developer mode is ON")
    TOKEN = os.environ["MISO_BOT_TOKEN_BETA"]
    prefix = "<"
else:
    TOKEN = os.environ["MISO_BOT_TOKEN"]
    prefix = ">"

if maintainance_mode:
    logger.info("Maintainance mode is ON")
    prefix = prefix * 2
    starting_activity = nextcord.Activity(
        type=nextcord.ActivityType.playing, name="Maintainance mode"
    )
else:
    starting_activity = nextcord.Activity(
        type=nextcord.ActivityType.playing, name="Booting up..."
    )


class MisoBot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.default_prefix = prefix
        self.logger = logger
        self.start_time = time()
        self.global_cd = commands.CooldownMapping.from_cooldown(
            15, 60, commands.BucketType.member
        )
        self.db = maria.MariaDB(self)
        self.cache = cache.Cache(self)
        self.version = "5.0"
        self.extensions_loaded = False

    async def close(self):
        await self.db.cleanup()
        await super().close()

    async def on_message(self, message):
        if not bot.is_ready():
            return

        await super().on_message(message)


bot = MisoBot(
    owner_id=133311691852218378,
    help_command=EmbedHelpCommand(),
    command_prefix=util.determine_prefix,
    case_insensitive=True,
    allowed_mentions=nextcord.AllowedMentions(everyone=False),
    max_messages=20000,
    heartbeat_timeout=180,
    intents=nextcord.Intents(
        guilds=True,
        members=True,  # requires verification
        bans=True,
        emojis=True,
        integrations=False,
        webhooks=False,
        invites=False,
        voice_states=False,
        presences=False,  # requires verification
        messages=True,
        reactions=True,
        typing=False,
    ),
    activity=starting_activity,
    status=nextcord.Status.idle,
)

maintainance_extensions = [
    "errorhandler",
    "owner",
]

extensions = [
    "errorhandler",
    "events",
    "configuration",
    "customcommands",
    "fishy",
    "information",
    # "rolepicker",
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
    "webserver",
    "reddit",
    "crypto",
    "kpop",
    "stats",
]

if maintainance_mode:
    extensions = maintainance_extensions


@bot.before_invoke
async def before_any_command(ctx):
    """Runs before any command"""
    ctx.timer = time()
    try:
        await ctx.trigger_typing()
    except nextcord.errors.Forbidden:
        pass


@bot.check
async def check_for_blacklist(ctx):
    """Check command invocation context for blacklist triggers"""
    return await util.is_blacklisted(ctx)


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


@bot.event
async def on_ready():
    if not bot.extensions_loaded:
        load_extensions()
        bot.boot_up_time = time() - bot.start_time
        logger.info(
            f"Boot up process completed in {util.stringfromtime(bot.boot_up_time)}"
        )
    latencies = bot.latencies
    logger.info(f"Loading complete | running {len(latencies)} shards")
    for shard_id, latency in latencies:
        logger.info(f"Shard [{shard_id}] - HEARTBEAT {latency}s")


def load_extensions():
    logger.info("Loading extensions...")
    for extension in extensions:
        try:
            bot.load_extension(f"cogs.{extension}")
            logger.info(f"Loaded [ {extension} ]")
        except Exception as error:
            logger.error(f"Error loading [ {extension} ]")
            traceback.print_exception(type(error), error, error.__traceback__)

    bot.load_extension("jishaku")
    bot.extensions_loaded = True
    logger.info("All extensions loaded successfully!")


def run():
    logger.info(f'Using default prefix "{prefix}"')
    bot.start_time = time()
    bot.run(TOKEN)


if __name__ == "__main__":
    run()
