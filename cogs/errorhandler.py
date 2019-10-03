from discord.ext import commands
import helpers.log as log
import traceback
from cogs.lastfm import LastFMError
from helpers import utilityfunctions as util

logger = log.get_logger(__name__)
command_logger = log.get_command_logger(showlevel=True)


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
            command_logger.error(log.log_command(ctx))
            logger.error(str(error))
            await ctx.send(f'`{ctx.command}` has been disabled!')

        elif isinstance(error, commands.NoPrivateMessage):
            command_logger.error(log.log_command(ctx))
            logger.error(str(error))
            await ctx.author.send(f'`{ctx.command}` can not be used in DMs!')

        elif isinstance(error, commands.NotOwner):
            command_logger.error(log.log_command(ctx))
            logger .error(str(error))
            await ctx.send(f"Sorry, you are not authorized to use this command!")

        elif isinstance(error, commands.MissingPermissions):
            command_logger.error(log.log_command(ctx))
            logger.error(str(error))
            perms = ', '.join([f"`{x}`" for x in error.missing_perms])
            await ctx.send(f"You require {perms} permission to use this command!")

        elif isinstance(error, commands.BotMissingPermissions):
            logger.error(str(error))
            perms = ', '.join([f"`{x}`" for x in error.missing_perms])
            await ctx.send(f"Cannot execute command! Missing permission {perms}")

        elif isinstance(error, commands.MissingRequiredArgument):
            command_logger.error(log.log_command(ctx))
            logger.error(str(error))
            await util.send_command_help(ctx)

        elif isinstance(error, commands.BadArgument):
            command_logger.error(log.log_command(ctx))
            await ctx.send(f"```{str(error)}```")

        elif isinstance(error, LastFMError):
            await ctx.send(f"```{str(error)}```")
        else:
            logger.error(f"Ignoring exception in command {ctx.command}:")
            traceback.print_exception(type(error), error, error.__traceback__)
            await ctx.send(f"```\n{type(error).__name__}: {str(error)}```")


def setup(client):
    client.add_cog(Events(client))
