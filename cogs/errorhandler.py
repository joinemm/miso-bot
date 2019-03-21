from discord.ext import commands
import helpers.log as log
import traceback

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()


class Events(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command.
        ctx   : Context
        error : Exception"""

        if hasattr(ctx.command, 'on_error'):
            return

        error = getattr(error, 'original', error)

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.DisabledCommand):
            logger.error(str(error))
            return await ctx.send(f'{ctx.command} has been disabled.')

        elif isinstance(error, commands.NoPrivateMessage):
            logger.error(str(error))
            return await ctx.author.send(f'{ctx.command} can not be used in Private Messages.')

        elif isinstance(error, commands.NotOwner):
            logger .error(str(error))
            owner = await self.client.application_info().owner
            return await ctx.send(f"Sorry, this command usable by the bot owner only! ({owner})")

        elif isinstance(error, commands.MissingPermissions):
            logger.error(str(error))
            perms = ', '.join([f"**{x}**" for x in error.missing_perms])
            return await ctx.send(f"You are missing the required permissions to use this command: {perms}")

        elif isinstance(error, commands.BotMissingPermissions):
            logger.error(str(error))
            perms = ', '.join([f"**{x}**" for x in error.missing_perms])
            return await ctx.send(f"I am missing the required permissions to execute this command: {perms}")

        elif isinstance(error, commands.MissingRequiredArgument):
            logger.error(str(error))
            return await ctx.send(f"**ERROR:** Missing required argument `{error.param}`")

        else:
            logger.error(f"Ignoring exception in command {ctx.command}:")
            traceback.print_exception(type(error), error, error.__traceback__)
            await ctx.send(f"```\n{type(error).__name__}: {str(error)}```")


def setup(client):
    client.add_cog(Events(client))
