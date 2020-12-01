import discord
import arrow
from discord.ext import commands
from helpers import utilityfunctions as util
from helpers import exceptions
import asyncio
from modules import queries


class Mod(commands.Cog):
    """Moderation commands"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🔨"

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
            async for message in ctx.channel.history(limit=500):
                if message.author in ctx.message.mentions:
                    deleted.append(message)
                    if len(deleted) >= amount:
                        break

            await ctx.channel.delete_messages(deleted)
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

        if duration is not None:
            duration = util.timefromstring(duration)
            if duration < 60:
                raise exceptions.Info("The minimum duration of a mute is **1 minute**")

        try:
            await member.add_roles(mute_role)
        except discord.errors.Forbidden:
            raise exceptions.Error(f"It seems I don't have permission to mute {member.mention}")

        await util.send_success(
            ctx,
            f"Muted {member.mention}"
            + (f" for **{util.stringfromtime(duration)}**" if duration is not None else ""),
        )

        if duration is not None:
            unmute_on = arrow.now().shift(seconds=+duration)
        else:
            unmute_on = None

        print(unmute_on)
        await self.bot.db.execute(
            """
            INSERT INTO muted_user (guild_id, user_id, unmute_on)
                VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                unmute_on = VALUES(unmute_on)
            """,
            ctx.guild.id,
            member.id,
            unmute_on,
        )

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
        await util.send_success(ctx, f"{channel.mention} is now blacklisted from command usage.")

    @blacklist.command(name="member")
    async def blacklist_member(self, ctx, *, member: discord.Member):
        """Blacklist member of this server."""
        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_member VALUES (%s, %s)", member.id, ctx.guild.id
        )
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
        await util.send_success(
            ctx, f"`{ctx.prefix}{cmd}` is now a blacklisted command on this server."
        )

    @blacklist.command(name="global")
    @commands.is_owner()
    async def blacklist_global(self, ctx, user: discord.User, *, reason):
        """Blacklist someone globally from Miso Bot."""
        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_user VALUES (%s, %s, %s)", user.id, reason
        )
        await util.send_success(ctx, f"**{user}** can no longer use Miso Bot!")

    @blacklist.command(name="guild")
    @commands.is_owner()
    async def blacklist_guild(self, ctx, guild_id: int, *, reason):
        """Blacklist a guild from adding or using Miso Bot."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise exceptions.Warning(f"Cannot find guild with id `{guild_id}`")

        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_guild VALUES (%s, %s)", guild.id, reason
        )
        await guild.leave()
        await util.send_success(ctx, f"**{guild}** can no longer use Miso Bot!")

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
        await util.send_success(ctx, f"{channel.mention} is no longer blacklisted.")

    @whitelist.command(name="user")
    async def whitelist_user(self, ctx, *, member: discord.Member):
        """Whitelist a member of this server."""
        await self.bot.db.execute(
            "DELETE FROM blacklisted_member WHERE guild_id = %s AND user_id = %s",
            ctx.guild.id,
            member.id,
        )
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
        await util.send_success(ctx, f"`{ctx.prefix}{cmd}` is no longer blacklisted.")

    @whitelist.command(name="global")
    @commands.is_owner()
    async def whitelist_global(self, ctx, *, user: discord.User):
        """Whitelist someone globally."""
        await self.bot.db.execute("DELETE FROM blacklisted_user WHERE user_id = %s", user.id)
        await util.send_success(ctx, f"**{user}** can now use Miso Bot again!")

    @whitelist.command(name="guild")
    @commands.is_owner()
    async def whitelist_guild(self, ctx, guild_id: int):
        """Whitelist a guild."""
        await self.bot.db.execute("DELETE FROM blacklisted_guild WHERE guild_id = %s", guild_id)
        await util.send_success(ctx, f"Guild with id `{guild_id}` can use Miso Bot again!")


def setup(bot):
    bot.add_cog(Mod(bot))
