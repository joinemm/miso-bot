import asyncio
from dataclasses import dataclass

import discord
from discord.ext import commands
from loguru import logger

from modules import emojis, exceptions, queries, util
from modules.misobot import MisoBot
from modules.tiktok import TiktokError


@dataclass
class ErrorMessages:
    disabled_command = "This command is temporarily disabled, sorry for the inconvenience!"
    no_private_message = "This command cannot be used in a DM!"
    missing_permissions = "You require {0} permission to use this command!"
    bot_missing_permissions = "Unable execute command due to missing permissions! (I need {0})"
    not_donator = "This command is exclusive to Miso Bot donators! Consider donating to get access"
    server_too_big = "This command cannot be used in large servers for performance reasons!"
    not_allowed = "You cannot use this command."
    max_concurrency = "Stop spamming! >:("
    command_on_cooldown = "You are on cooldown! Please wait `{0:.0f} seconds.`"


class ErrorHander(commands.Cog):
    """Any errors during command invocation will propagate here"""

    def __init__(self, bot):
        self.bot: MisoBot = bot

    def log_format(
        self, ctx: commands.Context, error: Exception | None, message: str | None = None
    ):
        return f"{ctx.guild} @ {ctx.author} : {ctx.message.content} => {type(error).__name__}: {message or str(error)}"

    async def reinvoke_command(self, ctx: commands.Context):
        try:
            await ctx.reinvoke()
            logger.info(util.log_command_format(ctx))
            if ctx.guild is not None:
                await queries.save_command_usage(ctx)
            return
        except commands.CommandError as e:
            return await self.on_command_error(ctx, e)

    async def send_embed(
        self,
        ctx: commands.Context,
        message: str,
        emoji: str = "",
        color: str | None = None,
        **kwargs,
    ):
        try:
            await ctx.send(
                embed=discord.Embed(
                    description=f"{emoji} {message}",
                    color=int(color, 16) if color else None,
                ),
                **kwargs,
            )
        except discord.Forbidden:
            logger.warning(f"403 Forbidden when trying to send error message : {message}")

    async def send_info(
        self, ctx: commands.Context, message: str, error: Exception | None = None, **kwargs
    ):
        logger.info(self.log_format(ctx, error, message))
        await self.send_embed(ctx, message, ":information_source:", "3b88c3", **kwargs)

    async def send_warning(
        self, ctx: commands.Context, message: str, error: Exception | None = None, **kwargs
    ):
        logger.warning(self.log_format(ctx, error, message))
        await self.send_embed(ctx, message, ":warning:", "ffcc4d", **kwargs)

    async def send_error(
        self,
        ctx: commands.Context,
        message: str,
        error: Exception | None = None,
        language="",
        **kwargs,
    ):
        logger.error(self.log_format(ctx, error, message))
        await self.send_embed(ctx, f"```{language}\n{message}```", color="be1931", **kwargs)

    async def send_lastfm_error(self, ctx: commands.Context, error: exceptions.LastFMError):
        match error.error_code:
            case 8:
                message = "There was a problem connecting to LastFM servers. LastFM might be down. Try again later."
            case 17:
                message = "Unable to get listening information. Please check you LastFM privacy settings."
            case 29:
                message = "LastFM rate limit exceeded. Please try again later."
            case _:
                message = error.display()

        logger.error(self.log_format(ctx, error, message))
        await self.send_embed(ctx, message, emojis.LASTFM, "b90000")

    async def handle_blacklist(self, ctx: commands.Context, error: exceptions.Blacklist):
        if ctx.author.id == ctx.bot.owner_id or (
            isinstance(
                error,
                (
                    exceptions.BlacklistedMember,
                    exceptions.BlacklistedChannel,
                    exceptions.BlacklistedCommand,
                ),
            )
            and isinstance(ctx.author, discord.Member)
            and (ctx.channel.permissions_for(ctx.author).administrator)
        ):
            # bypass the blacklist
            await self.reinvoke_command(ctx)
            return

        delete = False
        if ctx.guild:
            delete = await self.bot.db.fetch_value(
                """
                SELECT delete_blacklisted_usage
                FROM guild_settings
                WHERE guild_id = %s
                """,
                ctx.guild.id,
            )

        await self.send_error(ctx, error.message, delete_after=(5 if delete else None))
        if delete:
            await asyncio.sleep(5)
            await ctx.message.delete()

    async def handle_cooldown(self, ctx: commands.Context, error: commands.CommandOnCooldown):
        if (
            ctx.author.id == ctx.bot.owner_id
            or await queries.is_donator(ctx, ctx.author, 2)
            or await queries.is_vip(self.bot, ctx.author)
        ):
            await self.reinvoke_command(ctx)
        else:
            await self.send_embed(
                ctx,
                ErrorMessages.command_on_cooldown.format(error.retry_after),
                ":hourglass_flowing_sand:",
                "ffe8b6",
            )

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error_wrapper: commands.CommandError):
        """The event triggered when an error is raised while invoking a command"""

        # extract the original error from the CommandError wrapper
        error = getattr(error_wrapper, "original", error_wrapper)

        # handle error based on it's type
        match error:
            case commands.CommandNotFound():
                return

            case exceptions.CommandInfo():
                await self.send_info(ctx, str(error), error)

            case exceptions.CommandWarning():
                await self.send_warning(ctx, str(error), error)

            case exceptions.CommandError():
                await self.send_error(ctx, str(error), error)

            case commands.DisabledCommand():
                await self.send_info(ctx, ErrorMessages.disabled_command, error)

            case commands.MissingRequiredArgument():
                await util.send_command_help(ctx)

            case commands.MissingPermissions():
                permissions = ", ".join(f"`{x}`" for x in error.missing_permissions)
                await self.send_warning(
                    ctx,
                    ErrorMessages.missing_permissions.format(permissions),
                    error,
                )

            case commands.BotMissingPermissions():
                permissions = ", ".join(f"`{x}`" for x in error.missing_permissions)
                await self.send_warning(
                    ctx,
                    ErrorMessages.bot_missing_permissions.format(permissions, error),
                )

            case commands.NoPrivateMessage():
                await self.send_warning(ctx, ErrorMessages.no_private_message, error)

            case commands.MaxConcurrencyReached():
                await self.send_warning(ctx, ErrorMessages.max_concurrency, error)

            case util.PatronCheckFailure():
                await self.send_warning(ctx, ErrorMessages.not_donator, error)

            case exceptions.ServerTooBig():
                await self.send_warning(ctx, ErrorMessages.server_too_big, error)

            case commands.NotOwner() | commands.CheckFailure():
                await self.send_warning(ctx, ErrorMessages.not_allowed, error)

            case discord.Forbidden():
                try:
                    await self.send_error(ctx, str(error), error)
                except discord.Forbidden:
                    try:
                        await ctx.message.add_reaction("🙊")
                    except discord.Forbidden:
                        logger.error(self.log_format(ctx, error))

            case commands.BadArgument():
                await self.send_warning(ctx, str(error), error)

            case exceptions.LastFMError():
                await self.send_lastfm_error(ctx, error)

            case exceptions.RendererError():
                await self.send_error(ctx, f"Rendering Error: {str(error)}", error)

            case exceptions.Blacklist():
                await self.handle_blacklist(ctx, error)

            case commands.CommandOnCooldown():
                await self.handle_cooldown(ctx, error)

            case TiktokError():
                await self.send_warning(ctx, f"TikTok Error: {error.message}")

            case _:
                await self.send_error(
                    ctx, f"{type(error).__name__}: {error}", error, language="ex"
                )
                logger.opt(exception=error).error("Unhandled exception traceback:")


async def setup(bot):
    await bot.add_cog(ErrorHander(bot))
