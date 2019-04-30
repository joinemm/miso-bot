import discord
from discord.ext import commands
import requests
import json
import math
import psutil
import time
import os
import arrow
import copy
import helpers.utilityfunctions as util


class Info(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.start_time = time.time()

    @commands.command()
    async def patreon(self, ctx):
        """Link to the patreon page"""
        await ctx.send("https://www.patreon.com/joinemm")

    @commands.command()
    async def patrons(self, ctx):
        """List the current patreons"""
        patrons = [381491116853166080, 121757433507872768]
        content = discord.Embed(title="Patreon supporters ❤")
        content.description = ""
        for x in patrons:
            user = self.client.get_user(x)
            content.description += f"\n{user or x}"
        await ctx.send(embed=content)

    @commands.command(name='info')
    async def info(self, ctx):
        """Get information about the bot"""
        appinfo = await self.client.application_info()
        membercount = sum(1 for x in self.client.get_all_members())
        info_embed = discord.Embed(title="Miso Bot | version 2.0",
                                   description=f"Created by {appinfo.owner.mention}\n\n"
                                   f"Use `{self.client.command_prefix}help` to get the list of commands, "
                                   f"or visit the documention website for more help."
                                   f"\n\nCurrently active in **{len(self.client.guilds)}** "
                                   f"servers totaling **{membercount}** unique users",
                                   colour=discord.Colour.red())

        info_embed.set_thumbnail(url=self.client.user.avatar_url)
        info_embed.add_field(name='Github', value='https://github.com/joinemm/Miso-bot-rewrite', inline=False)
        info_embed.add_field(name='Documentation', value="http://joinemm.me/misobot", inline=False)
        info_embed.add_field(name='Patreon', value="https://www.patreon.com/joinemm", inline=False)

        await ctx.send(embed=info_embed)

    @commands.command()
    async def ping(self, ctx):
        """Get the bot's ping"""
        pong_msg = await ctx.send(":ping_pong:")
        sr_lat = (pong_msg.created_at - ctx.message.created_at).total_seconds() * 1000
        await pong_msg.edit(content=f"Command latency = `{sr_lat}ms`\n"
                                    f"API heartbeat = `{self.client.latency * 1000:.1f}ms`")

    @commands.command(aliases=['uptime'])
    async def status(self, ctx):
        """Get the bot's status"""
        up_time = time.time() - self.start_time
        uptime_string = util.stringfromtime(up_time)

        stime = time.time() - psutil.boot_time()
        system_uptime_string = util.stringfromtime(stime)

        mem = psutil.virtual_memory()
        pid = os.getpid()
        memory_use = psutil.Process(pid).memory_info()[0]

        content = discord.Embed(title=f"Miso Bot | version 2.0")
        content.set_thumbnail(url=self.client.user.avatar_url)

        content.add_field(name="Bot process uptime", value=uptime_string)
        content.add_field(name="System CPU Usage", value=f"{psutil.cpu_percent()}%")
        content.add_field(name="System uptime", value=system_uptime_string)
        content.add_field(name="System RAM Usage", value=f"{mem.percent}%")
        content.add_field(name="Bot memory usage", value=f"{memory_use / math.pow(1024, 2):.2f}MB")

        await ctx.send(embed=content)

    @commands.command()
    async def changelog(self, ctx):
        author = "joinemm"
        repo = "Miso-bot-rewrite"
        data = get_commits(author, repo)
        content = discord.Embed(color=discord.Color.from_rgb(255, 255, 255))
        content.set_author(name="Github commit history", icon_url=data[0]['author']['avatar_url'],
                           url=f"https://github.com/{author}/{repo}/commits/master")
        content.set_thumbnail(url='http://www.logospng.com/images/182/github-icon-182553.png')

        pages = []
        i = 0
        for commit in data:
            if i == 10:
                pages.append(content)
                content = copy.deepcopy(content)
                content.clear_fields()
                i = 0
            sha = commit['sha'][:7]
            author = commit['author']['login']
            date = commit['commit']['author']['date']
            arrow_date = arrow.get(date)
            url = commit['html_url']
            content.add_field(name=f"[`{sha}`] **{commit['commit']['message']}**",
                              value=f"**{author}** committed {arrow_date.humanize()} | [link]({url})",
                              inline=False)
            i += 1
        pages.append(content)
        await util.page_switcher(ctx, pages)


def setup(client):
    client.add_cog(Info(client))


def get_commits(author, repository):
    url = f"https://api.github.com/repos/{author}/{repository}/commits"
    response = requests.get(url)
    data = json.loads(response.content.decode('utf-8'))
    return data
