from discord.ext import commands
import os
import helpers.log as log
import data.database as db

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()

TOKEN = os.environ.get('MISO_BOT_TOKEN')
client = commands.Bot(command_prefix='>', case_insensitive=True)

extensions = ['cogs.events', 'cogs.config', 'cogs.errorhandler', 'cogs.customcommands', 'cogs.fishy', 'cogs.info',
              'cogs.rolepicker', 'cogs.mod', 'cogs.owner', 'cogs.notifications', 'cogs.miscellaneous', 'cogs.media',
              'cogs.lastfm', 'cogs.user', 'cogs.images', 'cogs.utility'
              ]


@client.event
async def on_ready():
    client.appinfo = await client.application_info()
    logger.info("Loading complete")


@client.before_invoke
async def before_any_command(ctx):
    await ctx.trigger_typing()
    if ctx.invoked_subcommand is None:
        command_logger.info(log.log_command(ctx))
        db.log_command_usage(ctx)

if __name__ == "__main__":
    for extension in extensions:
        try:
            client.load_extension(extension)
            logger.info(f"{extension} loaded successfully")
        except Exception as error:
            logger.error(f"{extension} loading failed [{error}]")

    client.run(TOKEN)
