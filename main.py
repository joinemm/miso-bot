from discord.ext import commands
import os
import helpers.log as log

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()

TOKEN = os.environ.get('MISO_BOT_TOKEN_BETA')
client = commands.Bot(command_prefix='<', case_insensitive=True)

extensions = ['cogs.events', 'cogs.config', 'cogs.errorhandler', 'cogs.customcommands', 'cogs.fishy', 'cogs.info',
              'cogs.rolepicker', 'cogs.mod', 'cogs.owner', 'cogs.notifications', 'cogs.miscellaneous', 'cogs.media',
              'cogs.chatbot', 'cogs.lastfm', 'cogs.user'
              ]


@client.event
async def on_ready():
    logger.info("Loading complete")


@client.before_invoke
async def before_any_command(ctx):
    if ctx.invoked_subcommand is None:
        command_logger.info(log.log_command(ctx))

if __name__ == "__main__":
    for extension in extensions:
        try:
            client.load_extension(extension)
            logger.info(f"{extension} loaded successfully")
        except Exception as error:
            logger.error(f"{extension} loading failed [{error}]")

    client.run(TOKEN)
