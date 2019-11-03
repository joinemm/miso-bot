import discord
import json
import math
import psutil
import time
import os
import arrow
import copy
import aiohttp
from discord.ext import commands
from operator import itemgetter
from helpers import utilityfunctions as util
from data import database as db


class Info(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.version = str(await get_version())

    @commands.command()
    async def invite(self, ctx):
        """Invite Miso to your server!"""
        url = discord.utils.oauth_url('500385855072894982', permissions=discord.Permissions(1074654407))
        await ctx.send(f">>> Use this link to invite me to your server!\n"
                       f"The selected permissions are **required** for everything to function properly, make sure to not disable any!\n<{url}>")

    @commands.command()
    async def patreon(self, ctx):
        """Link to the patreon page."""
        await ctx.send("https://www.patreon.com/joinemm")

    @commands.command()
    async def patrons(self, ctx):
        """List the current patreons."""
        patrons = db.query("select user_id, currently_active from patrons")
        content = discord.Embed(title="Patreon supporters ❤", color=discord.Color.red())
        current = []
        past = []
        for x in patrons:
            user = self.bot.get_user(x[0])
            if util.int_to_bool(x[1]):
                current.append(user or x[0])
            else:
                past.append(user or x[0])

        if current:
            content.add_field(name="Current patrons", value="\n".join([f"**{x}**" for x in current]))
        if past:
            content.add_field(name="Inactive patrons", value="\n".join([f"**{x}**" for x in past]))

        await ctx.send(embed=content)

    @commands.command(name='info')
    async def info(self, ctx):
        """Get information about the bot."""
        membercount = len(set(self.bot.get_all_members()))
        content = discord.Embed(title=f"Miso Bot | version {self.version}", colour=discord.Colour.red())
        content.description = (
            f"Created by **{self.bot.owner}** {self.bot.owner.mention} using discord.py and sqlite3\n\n"
            f"Use `{ctx.prefix}help` to get the full list of commands, \n"
            f"or visit the website for more detailed instructions.\n\n"
            f"Currently active in **{len(self.bot.guilds)}** servers, "
            f"totaling **{membercount}** unique users."
        )
        content.set_thumbnail(url=self.bot.user.avatar_url)
        content.add_field(name='Github', value='https://github.com/joinemm/miso-bot', inline=False)
        content.add_field(name='Website', value="https://misobot.xyz", inline=False)
        content.add_field(name='Patreon', value="https://www.patreon.com/joinemm", inline=False)

        data = await get_commits("joinemm", "miso-bot")
        last_update = data[0]['commit']['author'].get('date')
        content.set_footer(text=f"Latest update: {arrow.get(last_update).humanize()}")

        await ctx.send(embed=content)

    @commands.command()
    async def ping(self, ctx):
        """Get the bot's ping."""
        pong_msg = await ctx.send(":ping_pong:")
        sr_lat = (pong_msg.created_at - ctx.message.created_at).total_seconds() * 1000
        await pong_msg.edit(content=f"Command latency = `{sr_lat}`ms\n"
                                    f"Discord latency = `{self.bot.latency * 1000:.1f}`ms")

    @commands.command(aliases=['uptime'])
    async def status(self, ctx):
        """Get the bot's status."""
        up_time = time.time() - self.start_time
        uptime_string = util.stringfromtime(up_time, 2)
        stime = time.time() - psutil.boot_time()
        system_uptime_string = util.stringfromtime(stime, 2)

        mem = psutil.virtual_memory()
        pid = os.getpid()
        memory_use = psutil.Process(pid).memory_info()[0]

        content = discord.Embed(title=f":robot: status", colour=discord.Colour.from_rgb(165, 172, 175))
        
        data = await get_commits("joinemm", "miso-bot")
        last_update = arrow.get(data[0]['commit']['author'].get('date')).humanize()

        content.description = (
            f"> **__Bot__**\n**Version**: {self.version}\n**Uptime**: {uptime_string}\n**Latest commit**: {last_update}\n**Memory used**: {memory_use / math.pow(1024, 2):.2f}MB\n"
            f"> **__System__**\n**Uptime**: {system_uptime_string}\n**CPU Usage**: {psutil.cpu_percent()}%\n**RAM Usage**: {mem.percent}%\n"
            f"> **__Discord__**\n**discord.py version**: {discord.__version__}\n**WebSocket latency**: {self.bot.latency * 1000:.1f}ms"
        )

        await ctx.send(embed=content)

    @commands.command()
    async def changelog(self, ctx, author='joinemm', repo='miso-bot'):
        """Github commit history."""
        data = await get_commits(author, repo)
        content = discord.Embed(color=discord.Color.from_rgb(46, 188, 79))
        content.set_author(
            name="Github commit history",
            icon_url=data[0]['author']['avatar_url'],
            url=f"https://github.com/{author}/{repo}/commits/master"
        )
        content.set_thumbnail(url='http://www.logospng.com/images/182/github-icon-182553.png')

        pages = []
        i = 0
        for commit in data:
            if i == 7:
                pages.append(content)
                content = copy.deepcopy(content)
                content.clear_fields()
                i = 0
            sha = commit['sha'][:7]
            author = commit['author'].get('login') if commit['author'] else 'UNKNOWN'
            date = commit['commit']['author'].get('date')
            arrow_date = arrow.get(date)
            url = commit['html_url']
            content.add_field(name=f"[`{sha}`] {commit['commit'].get('message')}",
                              value=f"**{author}** committed {arrow_date.humanize()} | [link]({url})",
                              inline=False)
            i += 1
        pages.append(content)
        await util.page_switcher(ctx, pages)

    @commands.command()
    async def inspect(self, ctx, snowflake: int):
        """Inspect discord snowflake."""
        guild = self.bot.get_guild(snowflake)
        if guild is None:
            guild = ctx.guild
            member = guild.get_member(snowflake)
            if member is None:
                user = self.bot.get_user(snowflake)
                if user is None:
                    channel = self.bot.get_channel(snowflake)
                    if channel is None:
                        role = guild.get_role(snowflake)
                        if role is None:
                            emoji = discord.utils.get(self.bot.emojis, id=snowflake)
                            if emoji is None:
                                result = None
                            else:
                                result = emoji
                        else:
                            result = role
                    else:
                        result = channel
                else:
                    result = user
            else:
                result = member
        else:
            result = guild

        classname = str(result.__class__).replace('class', '').strip("<' >")
        content = discord.Embed(
            title=f":mag_right: {classname}",
            color=discord.Color.from_rgb(189, 221, 244)
        )
        if result is None:
            result_formatted = result
        else:
            result_formatted = ""
            for thing in result.__slots__:
                thing_value = getattr(result, thing)
                result_formatted += f"{thing}: {thing_value}\n"

        content.description = f"```yaml\n{result_formatted}\n```"
        await ctx.send(embed=content)

    @commands.command()
    async def commandstats(self, ctx, *args):
        """See the most used commands by you, the server, or globally

        Usage:
            >commandstats
            >commandstats my
            >commandstats global
            >commandstats my global
        """
        content = discord.Embed(color=discord.Color.from_rgb(165, 172, 175))
        globaldata = 'global' in args
        mydata = 'my' in args

        content.title = f"`>_` Most used commands" \
                        + ("" if globaldata else f" in {ctx.guild}") \
                        + (f" by {ctx.author}" if mydata else "")

        if globaldata:
            if mydata:
                data = db.query("SELECT command, SUM(count) FROM command_usage WHERE user_id = ?"
                                "GROUP BY command", (ctx.author.id,))
            else:
                data = db.query("SELECT command, SUM(count) FROM command_usage "
                                "GROUP BY command")
        else:
            if mydata:
                data = db.query("SELECT command, SUM(count) FROM command_usage WHERE guild_id = ? AND user_id = ?"
                                "GROUP BY command", (ctx.guild.id, ctx.author.id))
            else:
                data = db.query("SELECT command, SUM(count) FROM command_usage WHERE guild_id = ? "
                                "GROUP BY command", (ctx.guild.id,))

        rows = []
        total = 0
        for command, count in sorted(data, key=itemgetter(1), reverse=True):
            total += count
            user = None
            biggest_user = (None, None)
            if not mydata:
                if globaldata:
                    biggest_user = db.query("SELECT user_id, MAX(count) AS highest FROM command_usage "
                                            "WHERE command = ?", (command,))[0]
                else:
                    biggest_user = db.query("SELECT user_id, MAX(count) AS highest FROM command_usage "
                                            "WHERE command = ? AND guild_id = ?", (command, ctx.guild.id))[0]
                user = self.bot.get_user(biggest_user[0])

            rows.append(f"**x**`{count}` **>{command}**"
                        + (f" ( `{biggest_user[1]}` by `{user}` )" if not mydata else ""))

        content.set_footer(text=f"Total {total} commands used")

        await util.send_as_pages(ctx, content, rows)


def setup(bot):
    bot.add_cog(Info(bot))

async def get_version():
    url = 'https://api.github.com/repos/joinemm/miso-bot/contributors'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    return (data[0].get('contributions')+1) * 0.01

async def get_commits(author, repository):
    url = f"https://api.github.com/repos/{author}/{repository}/commits"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    return data
