from discord.ext import commands
import discord
import helpers.log as log
import helpers.utilityfunctions as util

logger = log.get_logger(__name__)


class Owner(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(hidden=True, rest_is_raw=True)
    @commands.is_owner()
    async def say(self, ctx, channel, *, message):
        """Make the bot say something in a given channel"""
        channel = await util.get_textchannel(ctx, channel)
        await channel.send(message)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def guilds(self, ctx):
        """Show all connected guilds"""
        membercount = len(set(self.client.get_all_members()))
        content = discord.Embed(title=f"Total **{len(self.client.guilds)}** guilds, **{membercount}** unique users")

        rows = []
        for guild in sorted(self.client.guilds, key=lambda x: x.member_count, reverse=True):
            rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def logout(self, ctx):
        """Shuts down the bot"""
        print('logout')
        await ctx.send("Shutting down... :wave:")
        await self.client.logout()


def setup(client):
    client.add_cog(Owner(client))
