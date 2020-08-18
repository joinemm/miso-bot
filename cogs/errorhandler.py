import traceback
import discord
import asyncio
from discord.ext import commands, flags
from helpers import exceptions, log, utilityfunctions as util
from data import database as db

logger = log.get_logger(__name__)
command_logger = log.get_logger("commands")


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command."""

        if hasattr(ctx.command, "on_error"):
            return

        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            return await util.send_command_help(ctx)

        command_logger.error(
            f'{type(error).__name__:25} > {ctx.guild} ? {ctx.author} "{ctx.message.content}" > {error}'
        )

        if isinstance(error, util.ErrorMessage):
            return await ctx.send(str(error))

        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(f"`{x}`" for x in error.missing_perms)
            return await ctx.send(
                f":warning: You require {perms} permission to use this command!"
            )

        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(f"`{x}`" for x in error.missing_perms)
            return await ctx.send(
                f":warning: Cannot execute command! Bot is missing permission {perms}"
            )

        elif isinstance(error, commands.CommandOnCooldown):
            if db.is_patron(ctx.author.id, (2, 3)):
                return await ctx.reinvoke()
            else:
                return await ctx.send(
                    f":hourglass: This command is on a cooldown! (`{error.retry_after:.2f}s` remaining)"
                )

        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(f":warning: `{ctx.command}` has been disabled!")

        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send(
                ":warning: You cannot use this command in private messages"
            )

        elif isinstance(error, util.PatronCheckFailure):
            await ctx.send(":no_entry: Support me on patreon to use this command! <https://patreon.com/joinemm>")

        elif isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            await ctx.send(
                ":warning: Sorry, you are not authorized to use this command!"
            )

        elif isinstance(error, exceptions.BlacklistTrigger):
            if error.blacklist_type == "command":
                message = "This command has been blacklisted by the server moderators"
            elif error.blacklist_type == "channel":
                message = "Command usage on this channel has been blacklisted by the server moderators"
            elif error.blacklist_type == "user":
                message = "You have been blacklisted from using commands by the server moderators"
            elif error.blacklist_type == "global":
                message = "You have been blacklisted from using Miso Bot"

            delete = error.do_delete
            await ctx.send(
                f":no_entry_sign: `{message}`", delete_after=(5 if delete else None)
            )
            if delete:
                await asyncio.sleep(5)
                await ctx.message.delete()

        elif isinstance(error, (commands.BadArgument, flags._parser.ArgumentParsingError)):
            await ctx.send(f"```{str(error)}```")

        elif isinstance(error, discord.errors.Forbidden):
            try:
                await ctx.send(f"```{str(error)}```")
            except discord.errors.Forbidden:
                try:
                    await ctx.message.add_reaction("🙊")
                except discord.errors.Forbidden:
                    logger.error(str(error))

        elif isinstance(error, exceptions.LastFMError):
            await ctx.send(f"```{str(error)}```")

        else:
            traceback.print_exception(type(error), error, error.__traceback__)
            await ctx.send(f"```\n{type(error).__name__}: {str(error)}```")


def setup(bot):
    bot.add_cog(Events(bot))
