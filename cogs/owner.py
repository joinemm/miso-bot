from discord.ext import commands
import discord
import helpers.log as log
import data.database as db
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
        membercount = sum(1 for x in self.client.get_all_members())
        content = f"__Total **{len(self.client.guilds)}** guilds, **{membercount}** unique users__"

        for guild in sorted(self.client.guilds, key=lambda x: x.member_count, reverse=True):
            content += f"\n[`{guild.id}`] **{guild.name}** - `{guild.member_count}` members"

        await ctx.send(content)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def logout(self, ctx):
        """Shuts down the bot"""
        print('logout')
        await ctx.send("Shutting down... :wave:")
        await self.client.logout()


def setup(client):
    client.add_cog(Owner(client))
