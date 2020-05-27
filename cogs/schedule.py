import discord
import arrow
from discord.ext import commands

class Schedule(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    async def schedule(self, ctx):
        pass

    @commands.group()
    async def event(self, ctx):
        pass

    @event.command(name='add')
    async def event_add(self, ctx, date, time, description):
        date = date.split('/')
        if len(date) == 3:
            d, m, y = date
        elif len(date) == 2:
            d, m = date
            y = arrow.now().year
        else:
            return ctx.send(":warning: Incorrect date format! use `day/month/year` or `day/month` (defaults to current year)")

        date = arrow.get(y, m, d)
        await ctx.send("`[ {date.format('MMMM DD YYYY')} | {timef} ]` {description}")
    

def setup(bot):
    bot.add_cog(Schedule(bot))
