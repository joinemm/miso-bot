import discord
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
from libraries import unicode_codes


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.version = f"{await get_version():.2f}"

    @commands.command()
    async def invite(self, ctx):
        """Invite Miso to your server!"""
        url = discord.utils.oauth_url(
            "500385855072894982", permissions=discord.Permissions(1074654407)
        )
        content = discord.Embed(title="Invite me to your server!")
        content.set_thumbnail(url=self.bot.user.avatar_url)
        content.add_field(
            name="Required permissions are selected automatically, don't touch them.",
            value=f"[Click here]({url})",
        )
        await ctx.send(embed=content)

    @commands.command()
    async def patreon(self, ctx):
        """Link to the patreon page."""
        await ctx.send("https://www.patreon.com/joinemm")

    @commands.command()
    async def kofi(self, ctx):
        """Link to the Ko-Fi page."""
        await ctx.send("https://ko-fi.com/joinemm")

    @commands.command()
    async def donate(self, ctx):
        """Donate to keep the bot running smoothly!"""
        content = discord.Embed(
            title="Donate to keep Miso Bot online!", colour=discord.Colour.orange()
        )
        content.add_field(name="Ko-Fi", value="https://ko-fi.com/joinemm", inline=False)
        content.add_field(name="Patreon", value="https://www.patreon.com/joinemm", inline=False)
        content.set_footer(text="Donations will be used to pay for server costs")
        await ctx.send(embed=content)

    @commands.command(aliases=["patrons", "supporters"])
    async def donators(self, ctx):
        """List of people who have donated."""
        tier_badges = [":coffee:", ":beer:", ":moneybag:", ":bank:"]
        patrons = db.query("select tier, user_id, currently_active from patrons")
        content = discord.Embed(
            title="Patreon supporters ❤",
            color=int("f96854", 16),
            description="https://patreon.com/joinemm\nhttps://ko-fi.com/joinemm",
        )
        current = []
        former = []
        for tier, user_id, state in sorted(patrons, key=lambda x: x[0], reverse=True):
            user = self.bot.get_user(user_id)

            if util.int_to_bool(state):
                current.append(f"**{user or user_id}** {tier_badges[tier-1]}")
            else:
                former.append(f"{user or user_id}")

        if current:
            content.add_field(inline=True, name="Current patrons", value="\n".join(current))

        if former:
            content.add_field(inline=True, name="Former patrons", value="\n".join(former))

        await ctx.send(embed=content)

    @commands.command(name="info")
    async def info(self, ctx):
        """Get information about the bot."""
        membercount = len(set(self.bot.get_all_members()))
        content = discord.Embed(
            title=f"Miso Bot | version {self.bot.version}", colour=discord.Colour.blue()
        )
        owner = self.bot.get_user(self.bot.owner_id)
        content.description = (
            f"Created by **{owner}** {owner.mention} using discord.py\n\n"
            f"Use `{ctx.prefix}help` to get help on any commands, \n"
            f"or visit the website for more detailed instructions.\n\n"
            f"Currently in **{len(self.bot.guilds)}** servers across **{len(self.bot.latencies)}** shards,\n"
            f"totalling **{membercount}** unique users."
        )
        content.set_thumbnail(url=self.bot.user.avatar_url)
        content.add_field(name="Website", value="https://misobot.xyz", inline=False)
        content.add_field(name="Github", value="https://github.com/joinemm/miso-bot", inline=False)
        content.add_field(name="Discord", value="https://discord.gg/RzDW3Ne", inline=False)

        data = await get_commits("joinemm", "miso-bot")
        last_update = data[0]["commit"]["author"].get("date")
        content.set_footer(text=f"Latest update: {arrow.get(last_update).humanize()}")

        await ctx.send(embed=content)

    @commands.command()
    async def ping(self, ctx):
        """Get the bot's ping."""
        test_message = await ctx.send(":ping_pong:")
        cmd_lat = (test_message.created_at - ctx.message.created_at).total_seconds() * 1000
        discord_lat = self.bot.latency * 1000
        content = discord.Embed(
            colour=discord.Color.red(),
            description=f"**Command response** `{cmd_lat}` ms\n"
            f"**Discord API latency** `{discord_lat:.1f}` ms",
        )
        await test_message.edit(content="", embed=content)

    @commands.command(aliases=["status"])
    async def system(self, ctx):
        """Get status of the system."""
        process_uptime = time.time() - self.bot.start_time
        system_uptime = time.time() - psutil.boot_time()
        mem = psutil.virtual_memory()
        pid = os.getpid()
        memory_use = psutil.Process(pid).memory_info()[0]

        data = [
            ("Version", self.bot.version),
            ("Process uptime", util.stringfromtime(process_uptime, 2)),
            ("Process memory", f"{memory_use / math.pow(1024, 2):.2f}MB"),
            ("System uptime", util.stringfromtime(system_uptime, 2)),
            ("CPU Usage", f"{psutil.cpu_percent()}%"),
            ("RAM Usage", f"{mem.percent}%"),
        ]

        content = discord.Embed(
            title=":computer: System status",
            colour=int("5dadec", 16),
            description="\n".join(f"**{x[0]}** {x[1]}" for x in data),
        )
        await ctx.send(embed=content)

    @commands.command(aliases=["shards"])
    async def shardinfo(self, ctx):
        """Get information about the current shards."""
        content = discord.Embed(title=f"Running {len(self.bot.shards)} shards")
        for shard in self.bot.shards.values():
            content.add_field(
                name=f"Shard [`{shard.id}`]"
                + (" :point_left:" if ctx.guild.shard_id == shard.id else ""),
                value=f"```Connected: {not shard.is_closed()}\nHeartbeat: {shard.latency * 1000:.2f} ms```",
            )

        await ctx.send(embed=content)

    @commands.command()
    async def changelog(self, ctx, author="joinemm", repo="miso-bot"):
        """Github commit history."""
        data = await get_commits(author, repo)
        content = discord.Embed(color=discord.Color.from_rgb(46, 188, 79))
        content.set_author(
            name="Github commit history",
            icon_url=data[0]["author"]["avatar_url"],
            url=f"https://github.com/{author}/{repo}/commits/master",
        )
        content.set_thumbnail(url="https://i.imgur.com/NomDwkT.png")

        pages = []
        i = 0
        for commit in data:
            if i == 10:
                pages.append(content)
                content = copy.deepcopy(content)
                content.clear_fields()
                i = 0

            i += 1
            sha = commit["sha"][:7]
            author = commit["commit"]["committer"]["name"]
            date = commit["commit"]["author"].get("date")
            arrow_date = arrow.get(date)
            url = commit["html_url"]
            content.add_field(
                name=commit["commit"].get("message"),
                value=f"`{author}` committed {arrow_date.humanize()} | [{sha}]({url})",
                inline=False,
            )

        pages.append(content)
        await util.page_switcher(ctx, pages)

    @commands.command()
    async def emojistats(self, ctx, scope="server"):
        """
        See most used emojis on server, globally, and optionally filtered by user.

        Usage:
            >emojistats
            >emojistats [mention]
            >emojistats global
            >emojistats global [mention]
        """
        g = scope == "global"
        usertarget = ctx.message.mentions[0] if ctx.message.mentions else None
        query = "SELECT emoji, sum(count), emojitype FROM emoji_usage"
        params = []
        if not g:
            query += " WHERE guild_id = ?"
            params.append(ctx.guild.id)

        if usertarget is not None:
            if not g:
                query += " AND user_id = ?"
            else:
                query += " WHERE user_id = ?"
            params.append(usertarget.id)

        query += " GROUP BY emoji ORDER BY sum(count) DESC"
        data = db.query(query, tuple(params))
        if data is None:
            return await ctx.send("No emojis found!")

        rows = []
        for i, (emoji, count, emojitype) in enumerate(data, start=1):
            if emojitype == "unicode":
                emoji_repr = unicode_codes.EMOJI_ALIAS_UNICODE.get(emoji)
            else:
                emoji_obj = self.bot.get_emoji(int(emoji.split(":")[-1].strip(">")))
                if emoji_obj is not None and emoji_obj.is_usable():
                    emoji_repr = str(emoji_obj)
                else:
                    emojiname = emoji.split(":")[0].strip("<")
                    if len(emojiname) < 2:
                        emojiname = emoji.split(":")[1]

                    emoji_repr = "`" + emojiname + "`"

            rows.append(f"`#{i:2}` {emoji_repr} — **{count}** Use" + ("s" if count > 1 else ""))

        content = discord.Embed(
            title="Most used emojis"
            + (f" by {usertarget.name}" if usertarget is not None else "")
            + (", globally" if g else " on this server"),
            color=int("ffcc4d", 16),
        )
        await util.send_as_pages(ctx, content, rows, maxrows=10)

    @commands.group()
    async def commandstats(self, ctx):
        """See the most used commands.

        Usage:
            >commandstats server [user]
            >commandstats global [user]
            >commandstats <command name>
        """
        if ctx.invoked_subcommand is None:
            args = ctx.message.content.split()[1:]
            if not args:
                await ctx.send(f"```{ctx.command.help}```")
            else:
                await self.commandstats_single(ctx, " ".join(args))

    @commandstats.command(name="server")
    async def commandstats_server(self, ctx, user: discord.Member = None):
        """Most used commands on this server."""
        content = discord.Embed(
            title=f"`>_` Most used commands in {ctx.guild.name}"
            + ("" if user is None else f" by {user}")
        )
        if user is not None:
            data = db.query(
                """SELECT command, SUM(count) FROM command_usage
                WHERE guild_id = ? AND user_id = ? GROUP BY command""",
                (ctx.guild.id, user.id),
            )
        else:
            data = db.query(
                """SELECT command, SUM(count) FROM command_usage
                WHERE guild_id = ? GROUP BY command""",
                (ctx.guild.id,),
            )

        rows = []
        total = 0
        for command, count in sorted(data, key=itemgetter(1), reverse=True):
            total += count
            biggest_user = None
            if user is None:
                userdata = db.query(
                    """SELECT user_id, MAX(count) AS highest FROM command_usage
                    WHERE command = ? AND guild_id = ?""",
                    (command, ctx.guild.id),
                )
                biggest_user = (self.bot.get_user(userdata[0][0]), userdata[0][1])

            rows.append(
                f"**{count}** x `>{command}`"
                + ("" if biggest_user is None else f" ( {biggest_user[1]} by {biggest_user[0]} )")
            )

        content.set_footer(text=f"Total {total} commands")
        await util.send_as_pages(ctx, content, rows)

    @commandstats.command(name="global")
    async def commandstats_global(self, ctx, user: discord.Member = None):
        """Most used commands globally."""
        content = discord.Embed(
            title="`>_` Most used commands" + ("" if user is None else f" by {user}")
        )
        if user is not None:
            data = db.query(
                """SELECT command, SUM(count) FROM command_usage
                WHERE user_id = ? GROUP BY command""",
                (user.id,),
            )
        else:
            data = db.query("""SELECT command, SUM(count) FROM command_usage GROUP BY command""")

        rows = []
        total = 0
        for command, count in sorted(data, key=itemgetter(1), reverse=True):
            total += count
            biggest_user = None
            if user is None:
                userdata = db.query(
                    """SELECT user_id, MAX(countsum) FROM (
                        SELECT user_id, SUM(count) as countsum FROM command_usage WHERE command = ? GROUP BY user_id
                    )""",
                    (command,),
                )
                biggest_user = (self.bot.get_user(userdata[0][0]), userdata[0][1])

            rows.append(
                f"**{count}** x `>{command}`"
                + ("" if biggest_user is None else f" ( {biggest_user[1]} by {biggest_user[0]} )")
            )

        content.set_footer(text=f"Total {total} commands")
        await util.send_as_pages(ctx, content, rows)

    async def commandstats_single(self, ctx, command_name):
        """Stats of a single command."""
        command = self.bot.get_command(command_name)
        if command is None:
            return await ctx.send(f"> Command `>{command_name}` does not exist.")

        content = discord.Embed(title=f"`>{command}`")

        command_name = str(command)

        # get data from database
        usage_data = db.query(
            """SELECT SUM(count) FROM command_usage WHERE command = ?""",
            (command_name,),
        )[0][0]

        usage_data_server = db.query(
            """SELECT SUM(count) FROM command_usage WHERE command = ? AND guild_id = ?""",
            (command_name, ctx.guild.id),
        )[0][0]

        most_uses_server = db.query(
            """SELECT guild_id, MAX(countsum) FROM (
                SELECT guild_id, SUM(count) as countsum FROM command_usage
                WHERE command = ? GROUP BY guild_id
            )""",
            (command_name,),
        )[0]

        most_uses_user = db.query(
            """SELECT user_id, MAX(countsum) FROM (
                SELECT user_id, SUM(count) as countsum FROM command_usage
                WHERE command = ? GROUP BY user_id
            )""",
            (command_name,),
        )[0]

        # show the data in embed fields
        content.add_field(name="Uses", value=usage_data)
        content.add_field(name="on this server", value=usage_data_server)
        content.add_field(
            name="Server most used in",
            value=f"{self.bot.get_guild(most_uses_server[0])} ({most_uses_server[1]})",
            inline=False,
        )
        content.add_field(
            name="Most total uses by",
            value=f"{self.bot.get_user(most_uses_user[0])} ({most_uses_user[1]})",
        )

        # additional data for command groups
        if hasattr(command, "commands"):
            content.description = "command group"
            subcommands_string = ", ".join(f"'{command.name} {x.name}'" for x in command.commands)
            subcommand_usage = db.query(
                """SELECT SUM(count) FROM command_usage WHERE command IN (%s)"""
                % subcommands_string
            )[0][0]
            content.add_field(inline=False, name="Total subcommand uses", value=subcommand_usage)

        await ctx.send(embed=content)

    @commands.command(aliases=["serverdp", "sdp"])
    async def servericon(self, ctx, guild: int = None):
        """Get discord guild icon."""
        if guild is not None:
            guild = self.bot.get_guild(guild)
        if guild is None:
            guild = ctx.guild

        content = discord.Embed()
        content.set_author(name=str(guild), url=guild.icon_url)
        content.set_image(url=guild.icon_url_as(static_format="png"))
        stats = await util.image_info_from_url(guild.icon_url)
        color = await util.color_from_image_url(str(guild.icon_url_as(size=128, format="png")))
        content.colour = await util.get_color(ctx, color)
        content.set_footer(
            text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
        )

        await ctx.send(embed=content)


def setup(bot):
    bot.add_cog(Info(bot))


async def get_version():
    url = "https://api.github.com/repos/joinemm/miso-bot/contributors"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    return (data[0].get("contributions") + 1) * 0.01


async def get_commits(author, repository):
    url = f"https://api.github.com/repos/{author}/{repository}/commits"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    return data
