import discord
from discord.ext import commands
import data.database as db
import helpers.errormessages as errormsg
import helpers.utilityfunctions as util
import asyncio


class Mod(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, user, *duration):
        """Mute user"""
        muterole = ctx.message.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
        if muterole is None:
            await ctx.send(f"Muterole for this server is invalid or not set, please use `>muterole` to set it.")
            return

        member = await util.get_member(ctx, user)
        if member is None:
            await ctx.send(errormsg.user_not_found(user))
            return

        if member.id == 133311691852218378:
            return await ctx.send("no.")

        t = None
        if duration:
            t = util.timefromstring(" ".join(duration))

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
        """Unmute user"""
        muterole = ctx.message.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
        if muterole is None:
            await ctx.send(f"Muterole for this server is invalid or not set, please use `>muterole` to set it.")
            return
        member = await util.get_member(ctx, user)
        if member is None:
            await ctx.send(errormsg.user_not_found(user))
            return
        await member.remove_roles(muterole)
        await ctx.send(f"Unmuted {member.mention}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user):
        """Ban user"""
        u = await util.get_user(ctx, user)
        if u is None:
            try:
                u = discord.Object(id=int(user))
            except ValueError:
                return await ctx.send(errormsg.user_not_found(user))

        if u.id == 133311691852218378:
            return await ctx.send("no.")

        content = discord.Embed(title="Ban user?", color=discord.Color.red())
        try:
            content.description = f"**{u.name}#{u.discriminator}** {u.mention}\n{u.id}"
        except AttributeError:
            # unknown user, most likely not in guild so just ban without confirmation
            await ctx.guild.ban(u)
            return await ctx.send(f"Banned `{u}`")

        # send confirmation message
        msg = await ctx.send(embed=content)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(_reaction, _user):
            return _reaction.message.id == msg.id and _reaction.emoji in ["✅", "❌"] \
                   and _user == ctx.author
        try:
            reaction, user = await self.client.wait_for('reaction_add', timeout=3600.0, check=check)
        except asyncio.TimeoutError:
            pass
        else:
            if reaction.emoji == "✅":
                await ctx.guild.ban(u)
            elif reaction.emoji == "❌":
                pass

        await msg.remove_reaction("✅", self.client.user)
        await msg.remove_reaction("❌", self.client.user)


def setup(client):
    client.add_cog(Mod(client))
