import asyncio

import discord
from discord.ext import commands
from loguru import logger

from modules import emojis, exceptions, queries, util
from modules.misobot import MisoBot


class ErrorHander(commands.Cog):
    """Any errors during command invocation will propagate here"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
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

    async def send(
        self,
        ctx: commands.Context,
        level,
        message,
        help_footer=None,
        codeblock=False,
        dm=False,
        **kwargs,
    ):
        """Send error message to chat"""
        settings = self.message_levels[level]
        if codeblock:
            message = f"`{message}`"

        embed = discord.Embed(
            color=settings["color"],
            description=f"{settings['description_prefix']} {message}",
        )

        help_footer = help_footer or settings["help_footer"]
        if help_footer and ctx.command:
            embed.set_footer(text=f"Learn more: {ctx.prefix}help {ctx.command.qualified_name}")

        try:
            target = ctx.author if dm else ctx
            await target.send(embed=embed, **kwargs)
        except discord.errors.Forbidden:
            logger.warning("Forbidden when trying to send error message embed")

    async def log_and_traceback(self, ctx: commands.Context, error):
        logger.opt(exception=error).error(
            f'Unhandled exception in command "{ctx.message.content}":'
        )
        await self.send(ctx, "error", f"{type(error).__name__}: {error}", codeblock=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        """The event triggered when an error is raised while invoking a command"""
        # ignore if command has it's own error handler
        if hasattr(ctx.command, "on_error"):
            return

        # extract the original error from the CommandError wrapper
        error = getattr(error, "original", error)

        # silently ignored expections
        if isinstance(error, (commands.CommandNotFound)):
            return

        if isinstance(error, commands.DisabledCommand):
            logger.warning(util.log_command_format(ctx, extra=str(error)))
            return await self.send(
                ctx,
                "info",
                "This command is temporarily disabled, sorry for the inconvenience!",
            )

        if isinstance(error, commands.MissingRequiredArgument):
            return await util.send_command_help(ctx)

        if isinstance(error, exceptions.CommandInfo):
            logger.info(util.log_command_format(ctx, extra=str(error)))
            return await self.send(ctx, "info", str(error), error.kwargs)
        if isinstance(error, exceptions.CommandWarning):
            logger.warning(util.log_command_format(ctx, extra=str(error)))
            return await self.send(ctx, "warning", str(error), error.kwargs)

        # following errors wont return and will log the error

        if isinstance(error, exceptions.CommandError):
            await self.send(ctx, "error", str(error), error.kwargs)

        if isinstance(error, commands.NoPrivateMessage):
            try:
                await self.send(ctx, "info", "This command cannot be used in DM", dm=True)
            except discord.HTTPException:
                pass

        elif isinstance(error, commands.MissingPermissions):
            perms = ", ".join(f"`{x}`" for x in error.missing_permissions)
            await self.send(ctx, "warning", f"You require {perms} permission to use this command!")

        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(f"`{x}`" for x in error.missing_permissions)
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
                f"You have to be a donator to use this command! See `{ctx.prefix}donate`",
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

        elif isinstance(error, discord.errors.Forbidden):
            try:
                await self.send(ctx, "error", str(error), codeblock=True)
            except discord.errors.Forbidden:
                try:
                    await ctx.message.add_reaction("🙊")
                except discord.errors.Forbidden:
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
                if isinstance(ctx.author, discord.Member):
                    perms = ctx.channel.permissions_for(ctx.author)
                    if perms.administrator or ctx.author.id == ctx.bot.owner_id:
                        try:
                            await ctx.reinvoke()
                            logger.info(util.log_command_format(ctx))
                            if ctx.guild is not None:
                                await queries.save_command_usage(ctx)
                            return
                        except Exception as e:
                            return await self.on_command_error(ctx, e)

            if ctx.guild:
                delete = await self.bot.db.fetch_value(
                    """
                    SELECT delete_blacklisted_usage FROM guild_settings WHERE guild_id = %s
                    """,
                    ctx.guild.id,
                )
            else:
                delete = False

            await self.send(ctx, "error", error.message, delete_after=(5 if delete else None))
            if delete:
                await asyncio.sleep(5)
                await ctx.message.delete()

        elif isinstance(error, commands.CommandOnCooldown):
            if await queries.is_donator(ctx, ctx.author, 2) or await queries.is_vip(
                self.bot, ctx.author
            ):
                try:
                    await ctx.reinvoke()
                    logger.info(util.log_command_format(ctx))
                    if ctx.guild is not None:
                        await queries.save_command_usage(ctx)
                    return
                except Exception as e:
                    return await self.on_command_error(ctx, e)
            else:
                await self.send(
                    ctx,
                    "cooldown",
                    f"You are on cooldown. Please wait `{error.retry_after:.0f} seconds`",
                )

        else:
            await self.log_and_traceback(ctx, error)

        logger.error(
            f"{ctx.guild} @ {ctx.author} : {ctx.message.content} => {type(error).__name__}: {error}"
        )


async def setup(bot):
    await bot.add_cog(ErrorHander(bot))
