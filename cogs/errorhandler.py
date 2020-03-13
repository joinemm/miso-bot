import traceback
import discord
from discord.ext import commands
from helpers import log, utilityfunctions as util
from cogs.lastfm import LastFMError

logger = log.get_logger(__name__)
command_logger = log.get_logger("commands")


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

        command_logger.error(f"{util.get_full_class_name(error):25} > {ctx.guild} ? {ctx.author} \"{ctx.message.content}\"")

        if isinstance(error, commands.CommandNotFound):
            return

        elif isinstance(error, commands.MissingPermissions):
            perms = ', '.join([f"`{x}`" for x in error.missing_perms])
            return await ctx.send(f":warning: You require {perms} permission to use this command!")

        elif isinstance(error, commands.BotMissingPermissions):
            perms = ', '.join([f"`{x}`" for x in error.missing_perms])
            return await ctx.send(f":warning: Cannot execute command! Bot is missing permission {perms}")

        elif isinstance(error, commands.MissingRequiredArgument):
            return await util.send_command_help(ctx)
        
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f":hourglass: This command is on a cooldown! (`{error.retry_after:.2f}s` remaining)")
        
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(f':warning: `{ctx.command}` has been disabled!')

        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send(f':warning: `{ctx.command}` can not be used in DMs!')

        elif isinstance(error, commands.NotOwner):
            await ctx.send(f":warning: Sorry, you are not authorized to use this command!")

        elif isinstance(error, commands.CheckFailure):
            logger.error(str(error))
            await ctx.send(f":warning: {error}")

        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"```{str(error)}```")
        
        elif isinstance(error, discord.errors.Forbidden):
            try:
                await ctx.message.add_reaction('🙊')
            except discord.errors.Forbidden:
                logger.error(str(error))

        elif isinstance(error, LastFMError):
            await ctx.send(f"```{str(error)}```")
        
        else:
            traceback.print_exception(type(error), error, error.__traceback__)
            await ctx.send(f"```\n{type(error).__name__}: {str(error)}```")


def setup(bot):
    bot.add_cog(Events(bot))
