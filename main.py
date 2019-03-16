from discord.ext import commands
import os
import helpers.log as log

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()

TOKEN = os.environ.get('MISO_BOT_TOKEN_BETA')
client = commands.Bot(command_prefix=">")

extensions = ['cogs.events', 'cogs.errorhandler', 'cogs.customcommands']


if __name__ == "__main__":
    for extension in extensions:
        try:
            client.load_extension(extension)
            logger.info(f"{extension} loaded successfully")
        except Exception as error:
            logger.error(f"{extension} loading failed [{error}]")
            pass

    client.run(TOKEN)
