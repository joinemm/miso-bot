from discord.ext import commands
import helpers.log as log

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()


class Events(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Loading complete")

    @commands.Cog.listener()
    async def before_any_command(self, ctx):
        command_logger.info(log.log_command(ctx))


def setup(client):
    client.add_cog(Events(client))
