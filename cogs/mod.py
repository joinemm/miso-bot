import asyncio

import arrow
import nextcord
from nextcord.ext import commands, tasks

from modules import exceptions, log, util

logger = log.get_logger(__name__)


class Mod(commands.Cog):
    """Moderation commands"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🔨"
        self.unmute_list = []
        self.cache_needs_refreshing = True
        self.unmute_loop.start()

    def cog_unload(self):
        self.unmute_loop.cancel()

    @tasks.loop(seconds=10.0)
    async def unmute_loop(self):
        try:
            await self.check_mutes()
        except Exception as e:
            logger.error(f"unmute loop error: {e}")

    @unmute_loop.before_loop
    async def before_unmute_loop(self):
        await self.bot.wait_until_ready()
        logger.info("Starting unmuting loop")

    async def check_mutes(self):
        """Check all current mutes"""
        if self.cache_needs_refreshing:
            self.cache_needs_refreshing = False
            self.unmute_list = await self.bot.db.execute(
                "SELECT user_id, guild_id, channel_id, unmute_on FROM muted_user WHERE unmute_on IS NOT NULL"
            )

        if not self.unmute_list:
            return

        now_ts = arrow.utcnow().int_timestamp
        for (user_id, guild_id, channel_id, unmute_on) in self.unmute_list:
            unmute_ts = unmute_on.int_timestamp
            if unmute_ts > now_ts:
                continue

            guild = self.bot.get_guild(guild_id)
            if guild is not None:
                user = guild.get_member(user_id)
            else:
                user = None
            if user is not None:
                mute_role_id = await self.bot.db.execute(
                    """
                    SELECT mute_role_id FROM guild_settings WHERE guild_id = %s
                    """,
                    guild.id,
                    one_value=True,
                )
                mute_role = guild.get_role(mute_role_id)
                if not mute_role:
                    return logger.warning("Mute role not set in unmuting loop")
                channel = guild.get_channel(channel_id)
                if channel is not None:
                    try:
                        await user.remove_roles(mute_role)
                    except nextcord.errors.Forbidden:
                        pass
                    try:
                        await channel.send(
                            embed=nextcord.Embed(
                                description=f":stopwatch: Unmuted {user.mention} (mute duration passed)",
                                color=int("66757f", 16),
                            )
                        )
                    except nextcord.errors.Forbidden:
                        logger.warning(
                            "Unable to send unmuting message due to missing permissions!"
                        )
            else:
                logger.info(
                    f"Deleted expired mute of unknown user {user_id} or unknown guild {guild_id}"
                )

            await self.bot.db.execute(
                """
                DELETE FROM muted_user
                    WHERE user_id = %s AND guild_id = %s
                """,
                user_id,
                guild_id,
            )
            self.cache_needs_refreshing = True

    @commands.command(aliases=["clean"], usage="<amount> [@mentions...]")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int):
        """
        Delete given amount of messages in the current channel

        Optionally if users are mentioned, only messages by those users are deleted.

        Usage:
            >purge <amount> [mentions...]
        """
        if amount > 100:
            raise exceptions.Warning("You cannot delete more than 100 messages at a time.")

        await ctx.message.delete()

        if ctx.message.mentions:
            deleted = []
            async for message in ctx.channel.history(limit=100, oldest_first=False):
                if message.author in ctx.message.mentions:
                    deleted.append(message)
                    if len(deleted) >= amount:
                        break
            try:
                await ctx.channel.delete_messages(deleted)
            except nextcord.errors.HTTPException:
                raise exceptions.Error("You can only delete messages that are under 14 days old.")
        else:
            deleted = await ctx.channel.purge(limit=amount)

        await ctx.send(
            f":put_litter_in_its_place: Deleted `{len(deleted)}` messages.",
            delete_after=5,
        )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: nextcord.Member, *, duration="1 hour"):
        """Timeout user. Pass 'remove' as the duration to remove"""
        if member.timeout is not None:
            seconds = member.timeout.timestamp() - arrow.now().int_timestamp
            if duration and duration.strip().lower() == "remove":
                await member.edit(timeout=None)
                return await util.send_success(ctx, f"Removed timeout from {member.mention}")
            else:
                raise exceptions.Info(
                    f"{member.mention} is already timed out (**{util.stringfromtime(seconds)}** remaining)",
                )

        seconds = util.timefromstring(duration)

        await member.edit(timeout=arrow.now().shift(seconds=+seconds).datetime)
        await util.send_success(
            ctx, f"Timed out {member.mention} for **{util.stringfromtime(seconds)}**"
        )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx: commands.Context, member: nextcord.Member, *, duration=None):
        """Mute user"""
        mute_role_id = await self.bot.db.execute(
            """
            SELECT mute_role_id FROM guild_settings WHERE guild_id = %s
            """,
            ctx.guild.id,
            one_value=True,
        )
        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            raise exceptions.Warning(
                "Mute role for this server has been deleted or is not set, "
                f"please use `{ctx.prefix}muterole <role>` to set it."
            )

        if member.id == 133311691852218378:
            return await ctx.send("no.")

        seconds = None
        if duration is not None:
            seconds = util.timefromstring(duration)

            if seconds is None or seconds == 0:
                raise exceptions.Warning(f'Invalid mute duration "{duration}"')

            if seconds < 60:
                raise exceptions.Info("The minimum duration of a mute is **1 minute**")

            if seconds > 604800:
                raise exceptions.Info("The maximum duration of a mute is **1 week**")

        try:
            await member.add_roles(mute_role)
        except nextcord.errors.Forbidden:
            raise exceptions.Error(f"It seems I don't have permission to mute {member.mention}")

        await util.send_success(
            ctx,
            f"Muted {member.mention}"
            + (f" for **{util.stringfromtime(seconds)}**" if seconds is not None else ""),
        )

        if seconds is not None:
            unmute_on = arrow.now().shift(seconds=+seconds).datetime
        else:
            unmute_on = None

        await self.bot.db.execute(
            """
            INSERT INTO muted_user (guild_id, user_id, channel_id, unmute_on)
                VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                unmute_on = VALUES(unmute_on)
            """,
            ctx.guild.id,
            member.id,
            ctx.channel.id,
            unmute_on,
        )
        self.cache_needs_refreshing = True

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx: commands.Context, member: nextcord.Member):
        """Unmute user"""
        mute_role_id = await self.bot.db.execute(
            """
            SELECT mute_role_id FROM guild_settings WHERE guild_id = %s
            """,
            ctx.guild.id,
            one_value=True,
        )
        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            raise exceptions.Warning(
                "Mute role for this server has been deleted or is not set, "
                f"please use `{ctx.prefix}muterole <role>` to set it."
            )
        try:
            await member.remove_roles(mute_role)
        except nextcord.errors.Forbidden:
            raise exceptions.Error(f"It seems I don't have permission to unmute {member.mention}")

        await util.send_success(ctx, f"Unmuted {member.mention}")
        await self.bot.db.execute(
            """
            DELETE FROM muted_user WHERE guild_id = %s AND user_id = %s
            """,
            ctx.guild.id,
            member.id,
        )
        self.cache_needs_refreshing = True

    @commands.command()
    async def inspect(self, ctx: commands.Context, *ids: int):
        """Resolve user ids into usernames"""
        if len(ids) > 25:
            raise exceptions.Warning("Only 25 at a time please!")
        rows = []
        for user_id in ids:
            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except nextcord.errors.NotFound:
                    user = None

            if user is None:
                rows.append(f"`{user_id}` -> ?")
            else:
                rows.append(f"`{user_id}` -> {user} {user.mention}")

        content = nextcord.Embed(
            title=f":face_with_monocle: Inspecting {len(ids)} users...",
            color=int("bdddf4", 16),
        )
        await util.send_as_pages(ctx, content, rows, maxrows=25)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def fastban(self, ctx: commands.Context, *discord_users):
        """Ban user(s) without confirmation box"""
        if not discord_users:
            return await util.send_command_help(ctx)

        for discord_user in discord_users:
            user = await util.get_user(ctx, discord_user)
            if user is None:
                try:
                    user = await self.bot.fetch_user(int(discord_user))
                except (ValueError, nextcord.NotFound):
                    await ctx.send(
                        embed=nextcord.Embed(
                            description=f":warning: Invalid user or id `{discord_user}`",
                            color=int("be1931", 16),
                        )
                    )
                    continue

            if user.id == 133311691852218378:
                return await ctx.send("no.")

            try:
                await ctx.guild.ban(user, delete_message_days=0)
            except nextcord.errors.Forbidden:
                await ctx.send(
                    embed=nextcord.Embed(
                        description=f":no_entry: It seems I don't have the permission to ban **{user}**",
                        color=int("be1931", 16),
                    )
                )
            else:
                await ctx.send(
                    embed=nextcord.Embed(
                        description=f":hammer: Banned `{user}`", color=int("f4900c", 16)
                    )
                )

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, *discord_users):
        """Ban user(s)"""
        if not discord_users:
            return await util.send_command_help(ctx)

        for discord_user in discord_users:
            user = await util.get_member(ctx, discord_user)
            if user is None:
                try:
                    user = await self.bot.fetch_user(int(discord_user))
                except (ValueError, nextcord.NotFound):
                    await ctx.send(
                        embed=nextcord.Embed(
                            description=f":warning: Invalid user or id `{discord_user}`",
                            color=int("be1931", 16),
                        )
                    )
                    continue

            if user.id == 133311691852218378:
                return await ctx.send("no.")

            # confirmation dialog for guild members
            if isinstance(user, nextcord.Member):
                await self.send_ban_confirmation(ctx, user)

            elif isinstance(user, nextcord.User):
                try:
                    await ctx.guild.ban(user, delete_message_days=0)
                except nextcord.errors.Forbidden:
                    await ctx.send(
                        embed=nextcord.Embed(
                            description=f":no_entry: It seems I don't have the permission to ban **{user}**",
                            color=int("be1931", 16),
                        )
                    )
                else:
                    await ctx.send(
                        embed=nextcord.Embed(
                            description=f":hammer: Banned `{user}`",
                            color=int("f4900c", 16),
                        )
                    )
            else:
                await ctx.send(
                    embed=nextcord.Embed(
                        description=f":warning: Invalid user or id `{discord_user}`",
                        color=int("be1931", 16),
                    )
                )

    async def send_ban_confirmation(self, ctx: commands.Context, user):
        content = nextcord.Embed(title=":hammer: Ban user?", color=int("f4900c", 16))
        content.description = f"{user.mention}\n**{user.name}#{user.discriminator}**\n{user.id}"
        msg = await ctx.send(embed=content)

        async def confirm_ban():
            try:
                await ctx.guild.ban(user, delete_message_days=0)
                content.title = ":white_check_mark: Banned user"
            except nextcord.errors.Forbidden:
                content.title = nextcord.Embed.Empty
                content.description = f":no_entry: It seems I don't have the permission to ban **{user}** {user.mention}"
                content.colour = int("be1931", 16)
            await msg.edit(embed=content)

        async def cancel_ban():
            content.title = ":x: Ban cancelled"
            await msg.edit(embed=content)

        functions = {"✅": confirm_ban, "❌": cancel_ban}
        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)
        )


def setup(bot):
    bot.add_cog(Mod(bot))
