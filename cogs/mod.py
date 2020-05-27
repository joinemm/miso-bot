import discord
import asyncio
from discord.ext import commands
from data import database as db
from helpers import utilityfunctions as util


class Mod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["clean"])
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        """Delete some amount of messages in current channel.
        If users are mentioned, only messages by those users are deleted.

        Usage:
            >purge <amount> [mentions...]"""
        if amount > 100:
            return await ctx.send(
                ":warning: You cannot bulk delete more than 100 messages."
            )

        await ctx.message.delete()

        if ctx.message.mentions:

            def user_check(m):
                return m.author in ctx.message.mentions

            deleted = []
            async for message in ctx.channel.history(limit=500):
                if user_check(message):
                    deleted.append(message)
                    if len(deleted) >= amount:
                        break

            await ctx.channel.delete_messages(deleted)
        else:
            deleted = await ctx.channel.purge(limit=amount)

        await ctx.send(
            f":put_litter_in_its_place: Deleted `{len(deleted)}` messages.",
            delete_after=4,
        )

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, user, *duration):
        """Mute user."""
        muterole = ctx.message.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
        if muterole is None:
            return await ctx.send(
                f"Muterole for this server is invalid or not set, please use `>muterole` to set it."
            )

        member = await util.get_member(ctx, user)
        if member is None:
            return await ctx.send(":warning: User `{user}` not found")

        if member.id == 133311691852218378:
            return await ctx.send("no.")

        t = None
        if duration:
            t = util.timefromstring(" ".join(duration))

        await member.add_roles(muterole)
        await ctx.send(
            f"Muted {member.mention}"
            + (f"for **{util.stringfromtime(t)}**" if t else "")
        )

        if t:
            await asyncio.sleep(t)
            if muterole in member.roles:
                await member.remove_roles(muterole)
                await ctx.send(
                    f"Unmuted {member.mention} (**{util.stringfromtime(t)}** passed)"
                )

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, user):
        """Unmute user."""
        muterole = ctx.message.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
        if muterole is None:
            return await ctx.send(
                "Muterole for this server is invalid or not set, please use `>muterole` to set it."
            )

        member = await util.get_member(ctx, user)
        if member is None:
            return await ctx.send(":warning: User `{user}` not found")

        await member.remove_roles(muterole)
        await ctx.send(f"Unmuted {member.mention}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user, delete_message_days: int = 0):
        """Ban user."""
        u = await util.get_user(ctx, user)
        if u is None:
            try:
                u = await self.bot.fetch_user(int(user))
            except (ValueError, discord.NotFound):
                return await ctx.send(f":warning: Invalid user or id `{user}`")

        if u.id == 133311691852218378:
            return await ctx.send("no.")

        content = discord.Embed(title=":hammer: Ban user?", color=discord.Color.red())
        try:
            content.description = f"{u.mention}\n**{u.name}#{u.discriminator}**\n{u.id}"
        except AttributeError:
            # unknown user, most likely not in guild so just ban without confirmation
            await ctx.guild.ban(u, delete_message_days=delete_message_days)
            return await ctx.send(f":hammer: Banned `{u}`")

        # send confirmation message
        msg = await ctx.send(embed=content)

        async def confirm_ban():
            content.title = ":white_check_mark: User banned"
            await msg.edit(embed=content)
            await ctx.guild.ban(u, delete_message_days=delete_message_days)

        async def cancel_ban():
            content.title = ":x: Ban cancelled"
            await msg.edit(embed=content)

        functions = {"✅": confirm_ban, "❌": cancel_ban}

        await util.reaction_buttons(
            ctx, msg, functions, only_author=True, single_use=True
        )

    @commands.group()
    @commands.has_permissions(administrator=True)
    async def blacklist(self, ctx):
        """Restrict command usage."""
        await util.command_group_help(ctx)

    @blacklist.command(name="delete")
    async def blacklist_delete(self, ctx, value: bool):
        """Toggle whether delete unsuccessful tries of command use"""
        db.update_setting(ctx.guild.id, "delete_blacklisted", util.bool_to_int(value))
        await ctx.send(
            f":white_check_mark: Deletion of unsuccessful command usage is now "
            f"**{'on' if value else 'off'}**"
        )

    @blacklist.command(name="show")
    async def blacklist_show(self, ctx):
        """Show current blacklists."""
        content = discord.Embed(title=f"{ctx.guild.name} Blacklist status")

        blacklisted_channels = db.get_blacklist(ctx.guild.id, "channel_id", "channels")
        blacklisted_users = db.get_blacklist(ctx.guild.id, "user_id", "users")
        blacklisted_commands = db.get_blacklist(ctx.guild.id, "command", "commands")

        if blacklisted_channels:
            content.add_field(
                name="Channels",
                value="\n".join(
                    f"<#{channel_id}>" for channel_id in blacklisted_channels
                ),
            )
        if blacklisted_users:
            content.add_field(
                name="Users",
                value="\n".join(f"<@{user_id}>" for user_id in blacklisted_users),
            )
        if blacklisted_commands:
            content.add_field(
                name="Commands",
                value="\n".join(f"`{command}`" for command in blacklisted_commands),
            )

        await ctx.send(embed=content)

    @blacklist.command(name="channel")
    async def blacklist_channel(self, ctx, textchannel: discord.TextChannel):
        """Blacklist a channel."""
        db.execute(
            "INSERT OR IGNORE INTO blacklisted_channels VALUES(?, ?)",
            (ctx.guild.id, textchannel.id),
        )
        await ctx.send(
            f":white_check_mark: {textchannel.mention} has been blacklisted from command usage"
        )

    @blacklist.command(name="user")
    async def blacklist_user(self, ctx, *, member: discord.Member):
        """Blacklist member of this server."""
        db.execute(
            "INSERT OR IGNORE INTO blacklisted_users VALUES(?, ?)",
            (ctx.guild.id, member.id),
        )
        await ctx.send(
            f":white_check_mark: **{member}** has been blacklisted from using commands on this server"
        )

    @blacklist.command(name="command")
    async def blacklist_command(self, ctx, *, command):
        """Blacklist a command."""
        cmd = self.bot.get_command(command)
        if cmd is None:
            return await ctx.send(f":warning: `{command}` is not a command!")

        db.execute(
            "INSERT OR IGNORE INTO blacklisted_commands VALUES(?, ?)",
            (ctx.guild.id, str(cmd)),
        )
        await ctx.send(
            f":white_check_mark: `{cmd}` has been blacklisted on this server"
        )

    @blacklist.command(name="global")
    @commands.is_owner()
    async def blacklist_global(self, ctx, *, user: discord.User):
        """Blacklist someone from Miso Bot"""
        db.execute("INSERT OR IGNORE INTO blacklist_global_users VALUES(?)", (user.id,))
        await ctx.send(
            f":white_check_mark: **{user}** is now globally blacklisted from using Miso Bot"
        )

    @commands.group()
    @commands.has_permissions(administrator=True)
    async def whitelist(self, ctx):
        """Reverse blacklist."""
        await util.command_group_help(ctx)

    @whitelist.command(name="channel")
    async def whitelist_channel(self, ctx, textchannel: discord.TextChannel):
        """Whitelist a channel."""
        db.execute(
            "DELETE FROM blacklisted_channels WHERE guild_id = ? AND channel_id = ?",
            (ctx.guild.id, textchannel.id),
        )
        await ctx.send(
            f":white_check_mark: {textchannel.mention} is no longer blacklisted"
        )

    @whitelist.command(name="user")
    async def whitelist_user(self, ctx, *, member: discord.Member):
        """Whitelist a member of this server."""
        db.execute(
            "DELETE FROM blacklisted_users WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id),
        )
        await ctx.send(f":white_check_mark: **{member}** is no longer blacklisted")

    @whitelist.command(name="command")
    async def whitelist_command(self, ctx, *, command):
        """Whitelist a command."""
        cmd = self.bot.get_command(command)
        if cmd is None:
            return await ctx.send(f":warning: `{command}` is not a command!")

        db.execute(
            "DELETE FROM blacklisted_commands WHERE guild_id = ? AND command = ?",
            (ctx.guild.id, str(cmd)),
        )
        await ctx.send(f":white_check_mark: `{cmd}` is no longer blacklisted")

    @whitelist.command(name="global")
    @commands.is_owner()
    async def whitelist_global(self, ctx, *, user: discord.User):
        """Whitelist user globally."""
        db.execute("DELETE FROM blacklist_global_users WHERE user_id = ?", (user.id,))
        await ctx.send(
            f":white_check_mark: **{user}** is no longer globally blacklisted from using Miso Bot"
        )


def setup(bot):
    bot.add_cog(Mod(bot))
