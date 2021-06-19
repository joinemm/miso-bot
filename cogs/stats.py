import os

import statcord
from discord.ext import commands


class StatcordPost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.token = os.environ.get("STATCORD_TOKEN")
        self.api = statcord.Client(self.bot, self.token)
        self.api.start_loop()

    @commands.Cog.listener()
    async def on_command(self, ctx):
        self.api.command_run(ctx)


def setup(bot):
    bot.add_cog(StatcordPost(bot))
