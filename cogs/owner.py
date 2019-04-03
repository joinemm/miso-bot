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
        content = "**Connected guilds:**\n"
        for guild in self.client.guilds:
            content += f"**{guild.name}** - {guild.member_count} users\n"
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
