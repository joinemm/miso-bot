import discord
import arrow
import asyncio
from discord.ext import commands, tasks
from modules import queries, exceptions, util, log


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
                "SELECT user_id, guild_id, channel_id, unmute_on FROM muted_user"
            )

        if not self.unmute_list:
            return

        now_ts = arrow.utcnow().timestamp
        for (user_id, guild_id, channel_id, unmute_on) in self.unmute_list:
            unmute_ts = unmute_on.timestamp()
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
                    except discord.errors.Forbidden:
                        pass
                    try:
                        await channel.send(
                            embed=discord.Embed(
                                description=f":stopwatch: Unmuted {user.mention} (mute duration passed)",
                                color=int("66757f", 16),
                            )
                        )
                    except discord.errors.Forbidden:
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

    @commands.command(aliases=["clean"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        """
        Delete some amount of messages in current channel.
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
            except discord.errors.HTTPException:
                raise exceptions.Error("You can only delete messages that are under 14 days old.")
        else:
            deleted = await ctx.channel.purge(limit=amount)

        await ctx.send(
            f":put_litter_in_its_place: Deleted `{len(deleted)}` messages.",
            delete_after=5,
        )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, *, duration=None):
        """Mute user."""
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
            elif seconds < 60:
                raise exceptions.Info("The minimum duration of a mute is **1 minute**")
            elif seconds > 604800:
                raise exceptions.Info("The maximum duration of a mute is **1 week**")

        try:
            await member.add_roles(mute_role)
        except discord.errors.Forbidden:
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
    async def unmute(self, ctx, member: discord.Member):
        """Unmute user."""
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
        except discord.errors.Forbidden:
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
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, *discord_users):
        """Ban user(s)."""
        if not discord_users:
            return await util.send_command_help(ctx)

        for discord_user in discord_users:
            user = await util.get_member(ctx, discord_user)
            if user is None:
                try:
                    user = await self.bot.fetch_user(int(discord_user))
                except (ValueError, discord.NotFound):
                    raise exceptions.Warning(f"Invalid user or id `{discord_user}`")

            if user.id == 133311691852218378:
                return await ctx.send("no.")

            # confirmation dialog for guild members
            if isinstance(user, discord.Member):
                await self.send_ban_confirmation(ctx, user)

            elif isinstance(user, discord.User):
                try:
                    await ctx.guild.ban(user)
                except discord.errors.Forbidden:
                    raise exceptions.Error(
                        f"It seems I don't have the permission to ban **{user}**"
                    )
                else:
                    await ctx.send(
                        embed=discord.Embed(
                            description=f":hammer: Banned `{user}`", color=int("f4900c", 16)
                        )
                    )
            else:
                raise exceptions.Warning(
                    f"There was an error finding discord user `{discord_user}`"
                )

    async def send_ban_confirmation(self, ctx, user):
        content = discord.Embed(title=":hammer: Ban user?", color=int("f4900c", 16))
        content.description = f"{user.mention}\n**{user.name}#{user.discriminator}**\n{user.id}"
        msg = await ctx.send(embed=content)

        async def confirm_ban():
            try:
                await ctx.guild.ban(user)
                content.title = ":white_check_mark: Banned user"
            except discord.errors.Forbidden:
                content.title = discord.Embed.Empty
                content.description = f":no_entry: It seems I don't have the permission to ban **{user}** {user.mention}"
                content.color = int("be1931", 16)
            await msg.edit(embed=content)

        async def cancel_ban():
            content.title = ":x: Ban cancelled"
            await msg.edit(embed=content)

        functions = {"✅": confirm_ban, "❌": cancel_ban}
        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)
        )

    @commands.group()
    @commands.has_permissions(manage_guild=True)
    async def blacklist(self, ctx):
        """Restrict command usage."""
        await util.command_group_help(ctx)

    @blacklist.command(name="delete")
    async def blacklist_delete(self, ctx, value: bool):
        """Toggle whether delete messages on blacklist trigger."""
        await queries.update_setting(ctx, "guild_settings", "delete_blacklisted_usage", value)
        if value:
            await util.send_success(ctx, "Now deleting messages that trigger any blacklists.")
        else:
            await util.send_success(ctx, "No longer deleting messages that trigger blacklists.")

    @blacklist.command(name="show")
    async def blacklist_show(self, ctx):
        """Show everything that's currently blacklisted."""
        content = discord.Embed(
            title=f":scroll: {ctx.guild.name} Blacklist", color=int("ffd983", 16)
        )

        blacklisted_channels = await self.bot.db.execute(
            """
            SELECT channel_id FROM blacklisted_channel WHERE guild_id = %s
            """,
            ctx.guild.id,
            as_list=True,
        )
        blacklisted_members = await self.bot.db.execute(
            """
            SELECT user_id FROM blacklisted_member WHERE guild_id = %s
            """,
            ctx.guild.id,
            as_list=True,
        )
        blacklisted_commands = await self.bot.db.execute(
            """
            SELECT command_name FROM blacklisted_command WHERE guild_id = %s
            """,
            ctx.guild.id,
            as_list=True,
        )

        def length_limited_value(rows):
            value = ""
            for row in rows:
                if len(value + "\n" + row) > 1019:
                    value += "\n..."
                    break
                else:
                    value += ("\n" if value != "" else "") + row
            return value

        if blacklisted_channels:
            rows = [f"<#{channel_id}>" for channel_id in blacklisted_channels]
            content.add_field(
                name="Channels",
                value=length_limited_value(rows),
            )
        if blacklisted_members:
            rows = [f"<@{user_id}>" for user_id in blacklisted_members]
            content.add_field(
                name="Users",
                value=length_limited_value(rows),
            )
        if blacklisted_commands:
            rows = [f"`{ctx.prefix}{command}`" for command in blacklisted_commands]
            content.add_field(
                name="Commands",
                value=length_limited_value(rows),
            )

        if not content.fields:
            content.description = "Nothing is blacklisted yet!"

        await ctx.send(embed=content)

    @blacklist.command(name="channel")
    async def blacklist_channel(self, ctx, *, channel: discord.TextChannel):
        """Blacklist a channel."""
        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_channel VALUES (%s, %s)", channel.id, ctx.guild.id
        )
        self.bot.cache.blacklist["global"]["channel"].add(channel.id)
        await util.send_success(ctx, f"{channel.mention} is now blacklisted from command usage.")

    @blacklist.command(name="member")
    async def blacklist_member(self, ctx, *, member: discord.Member):
        """Blacklist member of this server."""
        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_member VALUES (%s, %s)", member.id, ctx.guild.id
        )
        try:
            self.bot.cache.blacklist[str(ctx.guild.id)]["member"].add(member.id)
        except KeyError:
            self.bot.cache.blacklist[str(ctx.guild.id)] = {
                "member": set([member.id]),
                "command": set(),
            }
        await util.send_success(
            ctx, f"**{member}** is now blacklisted from using commands on this server."
        )

    @blacklist.command(name="command")
    async def blacklist_command(self, ctx, *, command):
        """Blacklist a command."""
        cmd = self.bot.get_command(command)
        if cmd is None:
            raise exceptions.Warning(f"Command `{ctx.prefix}{command}` not found.")

        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_command VALUES (%s, %s)", cmd.qualified_name, ctx.guild.id
        )
        try:
            self.bot.cache.blacklist[str(ctx.guild.id)]["command"].add(cmd.qualified_name.lower())
        except KeyError:
            self.bot.cache.blacklist[str(ctx.guild.id)] = {
                "member": set(),
                "command": set([cmd.qualified_name.lower()]),
            }
        await util.send_success(
            ctx, f"`{ctx.prefix}{cmd}` is now a blacklisted command on this server."
        )

    @blacklist.command(name="global")
    @commands.is_owner()
    async def blacklist_global(self, ctx, user: discord.User, *, reason):
        """Blacklist someone globally from MONDAY Bot."""
        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_user VALUES (%s, %s)", user.id, reason
        )
        self.bot.cache.blacklist["global"]["user"].add(user.id)
        await util.send_success(ctx, f"**{user}** can no longer use MONDAY Bot!")

    @blacklist.command(name="guild")
    @commands.is_owner()
    async def blacklist_guild(self, ctx, guild_id: int, *, reason):
        """Blacklist a guild from adding or using MONDAY Bot."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise exceptions.Warning(f"Cannot find guild with id `{guild_id}`")

        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_guild VALUES (%s, %s)", guild.id, reason
        )
        self.bot.cache.blacklist["global"]["guild"].add(guild_id)
        await guild.leave()
        await util.send_success(ctx, f"**{guild}** can no longer use MONDAY Bot!")

    @commands.group()
    @commands.has_permissions(administrator=True)
    async def whitelist(self, ctx):
        """Reverse blacklist."""
        await util.command_group_help(ctx)

    @whitelist.command(name="channel")
    async def whitelist_channel(self, ctx, *, channel: discord.TextChannel):
        """Whitelist a channel."""
        await self.bot.db.execute(
            "DELETE FROM blacklisted_channel WHERE guild_id = %s AND channel_id = %s",
            ctx.guild.id,
            channel.id,
        )
        self.bot.cache.blacklist["global"]["channel"].discard(channel.id)
        await util.send_success(ctx, f"{channel.mention} is no longer blacklisted.")

    @whitelist.command(name="user")
    async def whitelist_user(self, ctx, *, member: discord.Member):
        """Whitelist a member of this server."""
        await self.bot.db.execute(
            "DELETE FROM blacklisted_member WHERE guild_id = %s AND user_id = %s",
            ctx.guild.id,
            member.id,
        )
        self.bot.cache.blacklist[str(ctx.guild.id)]["member"].discard(member.id)
        await util.send_success(ctx, f"**{member}** is no longer blacklisted.")

    @whitelist.command(name="command")
    async def whitelist_command(self, ctx, *, command):
        """Whitelist a command."""
        cmd = self.bot.get_command(command)
        if cmd is None:
            raise exceptions.Warning(f"Command `{ctx.prefix}{command}` not found.")

        await self.bot.db.execute(
            "DELETE FROM blacklisted_command WHERE guild_id = %s AND command_name = %s",
            ctx.guild.id,
            cmd.qualified_name,
        )
        self.bot.cache.blacklist[str(ctx.guild.id)]["command"].discard(cmd.qualified_name.lower())
        await util.send_success(ctx, f"`{ctx.prefix}{cmd}` is no longer blacklisted.")

    @whitelist.command(name="global")
    @commands.is_owner()
    async def whitelist_global(self, ctx, *, user: discord.User):
        """Whitelist someone globally."""
        await self.bot.db.execute("DELETE FROM blacklisted_user WHERE user_id = %s", user.id)
        self.bot.cache.blacklist["global"]["user"].discard(user.id)
        await util.send_success(ctx, f"**{user}** can now use MONDAY Bot again!")

    @whitelist.command(name="guild")
    @commands.is_owner()
    async def whitelist_guild(self, ctx, guild_id: int):
        """Whitelist a guild."""
        await self.bot.db.execute("DELETE FROM blacklisted_guild WHERE guild_id = %s", guild_id)
        self.bot.cache.blacklist["global"]["guild"].discard(guild_id)
        await util.send_success(ctx, f"Guild with id `{guild_id}` can use MONDAY Bot again!")


def setup(bot):
    bot.add_cog(Mod(bot))
