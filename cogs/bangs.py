import aiohttp
from time import time
import discord
from discord.ext import commands
from helpers import log
from data import database as db

command_logger = log.get_command_logger()


class Bangs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """only for CommandNotFound."""
        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            if ctx.message.content.startswith(f"{ctx.prefix}!"):
                ctx.timer = time()
                ctx.iscallback = True
                ctx.command = self.bot.get_command("!")
                await ctx.command.callback(self, ctx)

    async def resolve_bang(self, ctx, bang, args):
        async with aiohttp.ClientSession() as session:
            params = {"q": "!" + bang + " " + args, "format": "json", "no_redirect": 1}
            url = "https://api.duckduckgo.com"
            async with session.get(url, params=params) as response:
                data = await response.json(content_type=None)
                location = data.get("Redirect")
                if location == "":
                    return await ctx.send(":warning: Unknown bang or found nothing!")

                while location:
                    response = await session.get(location)
                    location = response.headers.get("location")

                await ctx.send(response.url)

    @commands.command(name="!")
    async def bang(self, ctx):
        """
        DuckDuckGo bangs.
        For list of all bangs please visit https://duckduckgo.com/bang

        Usage:
            >!<bang> <query...>

        Example:
            >!w horses
        """
        if not hasattr(ctx, "iscallback"):
            return await ctx.send_help(ctx.command)

        try:
            await ctx.trigger_typing()
        except discord.errors.Forbidden:
            pass

        command_logger.info(log.log_command(ctx))
        db.log_command_usage(ctx)
        try:
            bang, args = ctx.message.content[len(ctx.prefix) + 1 :].split(" ", 1)
            if len(bang) != 0:
                await self.resolve_bang(ctx, bang, args)
        except ValueError:
            await ctx.send("Please provide a query to search")


def setup(bot):
    bot.add_cog(Bangs(bot))
