import discord
import asyncio
from discord.ext import commands
from data import database as db
from helpers import utilityfunctions as util


class Mod(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, user, *, duration):
        """Mute user."""
        muterole = ctx.message.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
        if muterole is None:
            return await ctx.send(f"Muterole for this server is invalid or not set, please use `>muterole` to set it.")

        member = await util.get_member(ctx, user)
        if member is None:
            return await ctx.send(":warning: User `{user}` not found")

        if member.id == 133311691852218378:
            return await ctx.send("no.")

        t = None
        if duration:
            t = util.timefromstring(duration)

        await member.add_roles(muterole)
        await ctx.send(f"Muted {member.mention}" + (f"for **{util.stringfromtime(t)}**" if t else ""))

        if t:
            await asyncio.sleep(t)
            if muterole in member.roles:
                await member.remove_roles(muterole)
                await ctx.send(f"Unmuted {member.mention} (**{util.stringfromtime(t)}** passed)")

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, user):
        """Unmute user."""
        muterole = ctx.message.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
        if muterole is None:
            return await ctx.send(f"Muterole for this server is invalid or not set, please use `>muterole` to set it.")

        member = await util.get_member(ctx, user)
        if member is None:
            return await ctx.send(":warning: User `{user}` not found")

        await member.remove_roles(muterole)
        await ctx.send(f"Unmuted {member.mention}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user):
        """Ban user."""
        u = await util.get_user(ctx, user)
        if u is None:
            try:
                u = await self.bot.fetch_user(int(user))
            except (ValueError, discord.NotFound):
                return await ctx.send(f":warning: Invalid user or id `{user}`")

        if u.id == 133311691852218378:
            return await ctx.send("no.")

        content = discord.Embed(
            title=":hammer: Ban user?",
            color=discord.Color.red()
        )
        try:
            content.description = f"{u.mention}\n**{u.name}#{u.discriminator}**\n{u.id}"
        except AttributeError as e:
            # unknown user, most likely not in guild so just ban without confirmation
            await ctx.guild.ban(u)
            return await ctx.send(f":hammer: Banned `{u}`")

        # send confirmation message
        msg = await ctx.send(embed=content)

        async def confirm_ban():
            content.title = ":white_check_mark: User banned"
            await msg.edit(embed=content)
            await ctx.guild.ban(u)

        async def cancel_ban():
            content.title = ":x: Ban cancelled"
            await msg.edit(embed=content)

        functions = {
            "✅": confirm_ban,
            "❌": cancel_ban
        }

        await util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)

def setup(bot):
    bot.add_cog(Mod(bot))
