import traceback
from discord.ext import commands
from helpers import log, utilityfunctions as util
from cogs.lastfm import LastFMError

logger = log.get_logger(__name__)


class Events(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command.

        ctx   : Context
        error : Exception
        """

        if hasattr(ctx.command, 'on_error'):
            return

        error = getattr(error, 'original', error)

        if isinstance(error, commands.CommandNotFound):
            return

        logger.error(f"Error in command {ctx.command}; {ctx.author} \"{ctx.message.content}\"")


        if isinstance(error, commands.DisabledCommand):
            logger.error(str(error))
            await ctx.send(f':warning: `{ctx.command}` has been disabled!')

        elif isinstance(error, commands.NoPrivateMessage):
            logger.error(str(error))
            await ctx.author.send(f':warning: `{ctx.command}` can not be used in DMs!')

        elif isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            logger .error(str(error))
            await ctx.send(f":warning: Sorry, you are not authorized to use this command!")

        elif isinstance(error, commands.MissingPermissions):
            logger.error(str(error))
            perms = ', '.join([f"`{x}`" for x in error.missing_perms])
            await ctx.send(f":warning: You require {perms} permission to use this command!")

        elif isinstance(error, commands.BotMissingPermissions):
            logger.error(str(error))
            perms = ', '.join([f"`{x}`" for x in error.missing_perms])
            await ctx.send(f":warning: Cannot execute command! Bot is missing permission {perms}")

        elif isinstance(error, commands.MissingRequiredArgument):
            logger.error(str(error))
            await util.send_command_help(ctx)

        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"```{str(error)}```")
        
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f":warning: This command has a cooldown! Please retry in `{error.retry_after:.2f}s` and spam less next time!")
        
        elif isinstance(error, LastFMError):
            await ctx.send(f"```{str(error)}```")
        else:
            traceback.print_exception(type(error), error, error.__traceback__)
            await ctx.send(f"```\n{type(error).__name__}: {str(error)}```")


def setup(bot):
    bot.add_cog(Events(bot))
