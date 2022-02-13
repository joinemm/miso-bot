import asyncio
import traceback

import nextcord
from nextcord.ext import commands

from modules import emojis, exceptions, log, queries, util

logger = log.get_logger(__name__)
command_logger = log.get_logger("commands")


class ErrorHander(commands.Cog):
    """Any errors during command invocation will propagate here"""

    def __init__(self, bot):
        self.bot = bot
        self.message_levels = {
            "info": {
                "description_prefix": ":information_source:",
                "color": int("3b88c3", 16),
                "help_footer": False,
            },
            "warning": {
                "description_prefix": ":warning:",
                "color": int("ffcc4d", 16),
                "help_footer": False,
            },
            "error": {
                "description_prefix": ":no_entry:",
                "color": int("be1931", 16),
                "help_footer": False,
            },
            "cooldown": {
                "description_prefix": ":hourglass_flowing_sand:",
                "color": int("ffe8b6", 16),
                "help_footer": False,
            },
            "lastfm": {
                "description_prefix": emojis.LASTFM,
                "color": int("b90000", 16),
                "help_footer": False,
            },
        }

    async def send(self, ctx, level, message, help_footer=None, codeblock=False, **kwargs):
        """Send error message to chat."""
        settings = self.message_levels.get(level)
        if codeblock:
            message = f"`{message}`"

        embed = nextcord.Embed(
            color=settings["color"],
            description=f"{settings['description_prefix']} {message}",
        )

        help_footer = help_footer or settings["help_footer"]
        if help_footer:
            embed.set_footer(text=f"Learn more: {ctx.prefix}help {ctx.command.qualified_name}")

        try:
            await ctx.send(embed=embed, **kwargs)
        except nextcord.errors.Forbidden:
            self.bot.logger.warning("Forbidden when trying to send error message embed")

    async def log_and_traceback(self, ctx, error):
        logger.error(f'Unhandled exception in command "{ctx.message.content}":')
        exc = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        logger.error(exc)
        await self.send(ctx, "error", f"{type(error).__name__}: {error}", codeblock=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command."""
        # ignore if command has it's own error handler
        if hasattr(ctx.command, "on_error"):
            return

        # extract the original error from the CommandError wrapper
        error = getattr(error, "original", error)

        # silently ignored expections
        if isinstance(error, (commands.CommandNotFound)):
            return

        if isinstance(error, commands.DisabledCommand):
            command_logger.warning(log.log_command(ctx, extra=error))
            return await self.send(
                ctx,
                "info",
                "This command is temporarily disabled, sorry for the inconvenience!",
            )

        if isinstance(error, commands.MissingRequiredArgument):
            return await util.send_command_help(ctx)

        if isinstance(error, exceptions.Info):
            command_logger.info(log.log_command(ctx, extra=error))
            return await self.send(ctx, "info", str(error), error.kwargs)
        if isinstance(error, exceptions.Warning):
            command_logger.warning(log.log_command(ctx, extra=error))
            return await self.send(ctx, "warning", str(error), error.kwargs)
        command_logger.error(
            f'{type(error).__name__:25} > {ctx.guild} : {ctx.author} "{ctx.message.content}" > {error}'
        )

        if isinstance(error, exceptions.Error):
            return await self.send(ctx, "error", str(error), error.kwargs)

        if isinstance(error, commands.NoPrivateMessage):
            try:
                await self.send(
                    ctx.author,
                    "info",
                    "This command cannot be used in DM",
                )
            except (nextcord.HTTPException, nextcord.errors.Forbidden):
                pass

        elif isinstance(error, commands.MissingPermissions):
            perms = ", ".join(f"**{x}**" for x in error.missing_permissions)
            await self.send(ctx, "warning", f"You require {perms} permission to use this command!")

        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(f"**{x}**" for x in error.missing_permissions)
            await self.send(
                ctx,
                "warning",
                f"Cannot execute command! Bot is missing permission {perms}",
            )

        elif isinstance(error, commands.errors.MaxConcurrencyReached):
            await ctx.send("Stop spamming! >:(")

        elif isinstance(error, commands.NoPrivateMessage):
            await self.send(ctx, "info", "You cannot use this command in private messages!")

        elif isinstance(error, util.PatronCheckFailure):
            await self.send(
                ctx,
                "error",
                "Support me on patreon to use this command! <https://patreon.com/joinemm>",
            )

        elif isinstance(error, exceptions.ServerTooBig):
            await self.send(
                ctx,
                "warning",
                "This command cannot be used in big servers!",
            )

        elif isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            await self.send(ctx, "error", "You cannot use this command.")

        elif isinstance(error, (commands.BadArgument)):
            await self.send(ctx, "warning", str(error), help_footer=True)

        elif isinstance(error, nextcord.errors.Forbidden):
            try:
                await self.send(ctx, "error", str(error), codeblock=True)
            except nextcord.errors.Forbidden:
                try:
                    await ctx.message.add_reaction("🙊")
                except nextcord.errors.Forbidden:
                    await self.log_and_traceback(ctx, error)

        elif isinstance(error, exceptions.LastFMError):
            if error.error_code == 8:
                message = "There was a problem connecting to LastFM servers. LastFM might be down. Try again later."
            elif error.error_code == 17:
                message = "Unable to get listening information. Please check you LastFM privacy settings."
            elif error.error_code == 29:
                message = "LastFM rate limit exceeded. Please try again later."
            else:
                message = error.display()

            await self.send(ctx, "lastfm", message)

        elif isinstance(error, exceptions.RendererError):
            await self.send(ctx, "error", "HTML Rendering error: " + str(error))

        elif isinstance(error, exceptions.Blacklist):
            # admins can bypass these blacklists
            if isinstance(
                error,
                (
                    exceptions.BlacklistedMember,
                    exceptions.BlacklistedChannel,
                    exceptions.BlacklistedCommand,
                ),
            ):
                perms = ctx.channel.permissions_for(ctx.author)
                if perms.administrator or ctx.author.id == ctx.bot.owner_id:
                    try:
                        await ctx.reinvoke()
                        return
                    except Exception as e:
                        return await self.on_command_error(ctx, e)

            delete = await self.bot.db.execute(
                "SELECT delete_blacklisted_usage FROM guild_settings WHERE guild_id = %s",
                ctx.guild.id,
                one_value=True,
            )
            await self.send(ctx, "error", error.message, delete_after=(5 if delete else None))
            if delete:
                await asyncio.sleep(5)
                await ctx.message.delete()

        elif isinstance(error, commands.CommandOnCooldown):
            if await queries.is_donator(ctx, ctx.author, 2):
                try:
                    await ctx.reinvoke()
                    return
                except Exception as e:
                    await self.on_command_error(ctx, e)
            else:
                await self.send(
                    ctx,
                    "cooldown",
                    f"You are on cooldown. Please wait `{error.retry_after:.0f} seconds`",
                )

        else:
            await self.log_and_traceback(ctx, error)


def setup(bot):
    bot.add_cog(ErrorHander(bot))
