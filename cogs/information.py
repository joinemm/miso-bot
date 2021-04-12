import discord
import math
import psutil
import time
import os
import arrow
import copy
import aiohttp
from discord.ext import commands
from libraries import emoji_literals, plotter
from modules import util, exceptions
from numpy import nan


class Information(commands.Cog):
    """See bot related information"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "ℹ️"

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
    async def github(self, ctx):
        """See the source code."""
        await ctx.send("https://github.com/joinemm/miso-bot")

    @commands.command(aliases=["patreon", "kofi", "sponsor", "ko-fi"])
    async def donate(self, ctx):
        """Donate to keep the bot running smoothly!"""
        content = discord.Embed(
            title="Consider donating to help keep Miso Bot online!", colour=discord.Colour.orange()
        )
        content.add_field(
            name="Github Sponsor", value="https://github.com/sponsors/joinemm", inline=False
        )
        content.add_field(name="Patreon", value="https://www.patreon.com/joinemm", inline=False)
        content.add_field(name="Ko-Fi", value="https://ko-fi.com/joinemm", inline=False)
        content.add_field(name="Bitcoin", value="`1HDwoc5ith4goXmh6CAQC3TP6i1GAqanB1`")
        content.set_footer(text="Donations will be used to pay for server and upkeep costs")
        await ctx.send(embed=content)

    @commands.command(aliases=["patrons", "supporters", "sponsors"])
    async def donators(self, ctx):
        """List of people who have donated."""
        patrons = await self.bot.db.execute(
            """
            SELECT user_id, currently_active, emoji, donation_tier, amount
            FROM donator LEFT OUTER JOIN donation_tier ON donation_tier=id
            """
        )
        content = discord.Embed(
            title=":heart: Miso Bot supporters",
            color=int("dd2e44", 16),
            description=" | ".join(
                [
                    "[github](https://github.com/sponsors/joinemm)",
                    "[patreon](https://patreon.com/joinemm)",
                    "[kofi](https://ko-fi.com/joinemm)",
                    "[paypal](https://paypal.me/joinemm)",
                ]
            ),
        )
        current = {}
        former = []
        for user_id, is_active, emoji, tier, amount in sorted(
            patrons, key=lambda x: x[3], reverse=False
        ):
            user = self.bot.get_user(user_id)
            if user is None:
                continue

            if is_active:
                try:
                    current[f"{emoji} ${int(amount)} Tier"].append(f"{user}")
                except KeyError:
                    current[f"{emoji} ${int(amount)} Tier"] = [f"{user}"]
            else:
                former.append(f"{user}")

        if current:
            for tier_name, users in current.items():
                content.add_field(inline=True, name=tier_name, value="\n".join(users))

        if former:
            content.add_field(inline=False, name="Former donators", value="\n".join(former))

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
    async def emojistats(self, ctx, user: discord.Member = None, *args):
        """See most used emojis on the server, optionally filtered by user."""
        global_user = False
        if "global" in [x.lower() for x in args] and user is not None:
            global_user = True
            custom_emojis = await self.bot.db.execute(
                """
                SELECT sum(uses), emoji_id, emoji_name
                    FROM custom_emoji_usage
                    WHERE user_id = %s
                GROUP BY emoji_id
                """,
                user.id,
            )
            default_emojis = await self.bot.db.execute(
                """
                SELECT sum(uses), emoji_name
                    FROM unicode_emoji_usage
                    WHERE user_id = %s
                GROUP BY emoji_name
                """,
                user.id,
            )
        else:
            opt = [] if user is None else [user.id]
            custom_emojis = await self.bot.db.execute(
                f"""
                SELECT sum(uses), emoji_id, emoji_name
                    FROM custom_emoji_usage
                    WHERE guild_id = %s
                    {'AND user_id = %s' if user is not None else ''}
                GROUP BY emoji_id
                """,
                ctx.guild.id,
                *opt,
            )
            default_emojis = await self.bot.db.execute(
                f"""
                SELECT sum(uses), emoji_name
                    FROM unicode_emoji_usage
                    WHERE guild_id = %s
                    {'AND user_id = %s' if user is not None else ''}
                GROUP BY emoji_name
                """,
                ctx.guild.id,
                *opt,
            )

        if not custom_emojis and not default_emojis:
            return await ctx.send("No emojis have been used yet!")

        all_emojis = []
        for uses, emoji_name in default_emojis:
            emoji_repr = emoji_literals.NAME_TO_UNICODE.get(emoji_name)
            all_emojis.append((uses, emoji_repr))

        for uses, emoji_id, emoji_name in custom_emojis:
            emoji = self.bot.get_emoji(int(emoji_id))
            if emoji is not None and emoji.is_usable():
                emoji_repr = str(emoji)
            else:
                emoji_repr = "`" + emoji_name + "`"
            all_emojis.append((uses, emoji_repr))

        rows = []
        for i, (uses, emoji_name) in enumerate(
            sorted(all_emojis, key=lambda x: x[0], reverse=True), start=1
        ):
            rows.append(f"`#{i:2}` {emoji_name} — **{uses}** Use" + ("s" if uses > 1 else ""))

        content = discord.Embed(
            title="Most used emojis"
            + (f" by {user.name}" if user is not None else "")
            + (" globally" if global_user else f" in {ctx.guild.name}"),
            color=int("ffcc4d", 16),
        )
        await util.send_as_pages(ctx, content, rows, maxrows=15)

    @commands.group()
    async def commandstats(self, ctx):
        """
        See statistics of command usage.
        Use commandstats <command name> for stats of a specific command.
        """
        if ctx.invoked_subcommand is None:
            args = ctx.message.content.split()[1:]
            if not args:
                await util.send_command_help(ctx)
            else:
                await self.commandstats_single(ctx, " ".join(args))

    @commandstats.command(name="server")
    async def commandstats_server(self, ctx, user: discord.Member = None):
        """Most used commands in this server."""
        content = discord.Embed(
            title=f":bar_chart: Most used commands in {ctx.guild.name}"
            + ("" if user is None else f" by {user}")
        )
        opt = []
        if user is not None:
            opt = [user.id]

        data = await self.bot.db.execute(
            f"""
            SELECT command_name, SUM(use_sum) as total FROM (
                SELECT command_name, SUM(uses) as use_sum, user_id FROM command_usage
                    WHERE command_type = 'internal'
                      AND guild_id = %s
                    {'AND user_id = %s' if user is not None else ''}
                GROUP BY command_name, user_id
            ) as subq
            GROUP BY command_name
            ORDER BY total DESC
            """,
            ctx.guild.id,
            *opt,
        )
        rows = []
        total = 0
        for i, (command_name, count) in enumerate(data, start=1):
            total += count
            rows.append(
                f"`#{i:2}` **{count}** use{'' if count == 1 else 's'} : `{ctx.prefix}{command_name}`"
            )

        if rows:
            content.set_footer(text=f"Total {total} commands")
            await util.send_as_pages(ctx, content, rows)
        else:
            content.description = "No data :("
            await ctx.send(embed=content)

    @commandstats.command(name="global")
    async def commandstats_global(self, ctx, user: discord.Member = None):
        """Most used commands globally."""
        content = discord.Embed(
            title=":bar_chart: Most used commands" + ("" if user is None else f" by {user}")
        )
        opt = []
        if user is not None:
            opt = [user.id]

        data = await self.bot.db.execute(
            f"""
            SELECT command_name, SUM(use_sum) as total FROM (
                SELECT command_name, SUM(uses) as use_sum, user_id FROM command_usage
                    WHERE command_type = 'internal'
                    {'AND user_id = %s' if user is not None else ''}
                GROUP BY command_name, user_id
            ) as subq
            GROUP BY command_name
            ORDER BY total DESC
            """,
            *opt,
        )
        rows = []
        total = 0
        for i, (command_name, count) in enumerate(data, start=1):
            total += count
            rows.append(
                f"`#{i:2}` **{count}** use{'' if count == 1 else 's'} : `{ctx.prefix}{command_name}`"
            )

        if rows:
            content.set_footer(text=f"Total {total} commands")
            await util.send_as_pages(ctx, content, rows)
        else:
            content.description = "No data :("
            await ctx.send(embed=content)

    async def commandstats_single(self, ctx, command_name):
        """Stats of a single command."""
        command = self.bot.get_command(command_name)
        if command is None:
            raise exceptions.Info(f"Command `{ctx.prefix}{command_name}` does not exist!")

        content = discord.Embed(title=f":bar_chart: `{ctx.prefix}{command.qualified_name}`")

        # set command name to be tuple of subcommands if this is a command group
        group = hasattr(command, "commands")
        if group:
            command_name = tuple(
                [f"{command.name} {x.name}" for x in command.commands] + [command_name]
            )
        else:
            command_name = command.qualified_name

        total_uses, most_used_by_user_id, most_used_by_user_amount = await self.bot.db.execute(
            f"""
            SELECT SUM(use_sum) as total, user_id, MAX(use_sum) FROM (
                SELECT SUM(uses) as use_sum, user_id FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name {'IN %s' if group else '= %s'}
                GROUP BY user_id
            ) as subq
            """,
            command_name,
            one_row=True,
        )

        most_used_by_guild_id, most_used_by_guild_amount = await self.bot.db.execute(
            f"""
            SELECT guild_id, MAX(use_sum) FROM (
                SELECT guild_id, SUM(uses) as use_sum FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name {'IN %s' if group else '= %s'}
                GROUP BY guild_id
            ) as subq
            """,
            command_name,
            one_row=True,
        )

        uses_in_this_server = (
            await self.bot.db.execute(
                f"""
                SELECT SUM(uses) FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name {'IN %s' if group else '= %s'}
                      AND guild_id = %s
                GROUP BY guild_id
                """,
                command_name,
                ctx.guild.id,
                one_value=True,
            )
            or 0
        )

        # show the data in embed fields
        content.add_field(name="Uses", value=total_uses or 0)
        content.add_field(name="on this server", value=uses_in_this_server)
        content.add_field(
            name="Server most used in",
            value=f"{self.bot.get_guild(most_used_by_guild_id)} ({most_used_by_guild_amount or 0})",
            inline=False,
        )
        content.add_field(
            name="Most total uses by",
            value=f"{self.bot.get_user(most_used_by_user_id)} ({most_used_by_user_amount or 0})",
        )

        # additional data for command groups
        if group:
            content.description = "Command Group"
            subcommands_tuple = tuple([f"{command.name} {x.name}" for x in command.commands])
            subcommand_usage = await self.bot.db.execute(
                """
                SELECT command_name, SUM(uses) FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name IN %s
                GROUP BY command_name ORDER BY SUM(uses) DESC
                """,
                subcommands_tuple,
            )
            content.add_field(
                name="Subcommand usage",
                value="\n".join(f"{s[0]} - **{s[1]}**" for s in subcommand_usage),
                inline=False,
            )

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
        if stats is not None:
            content.set_footer(
                text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
            )

        await ctx.send(embed=content)

    @commands.command()
    async def stats(self, ctx):
        """See bot stats."""
        content = discord.Embed(
            title=":bar_chart: Events since last reboot",
            description="",
            color=int("5c913b", 16),
        )
        for event, count in self.bot.cache.event_triggers.items():
            content.description += f"\n`on_{event}`: **{count}**"
        await ctx.send(embed=content)

    @commands.command()
    async def statsgraph(self, ctx, stat, hours: int = 24):
        stat = stat.lower()
        available = [
            "messages",
            "reactions",
            "commands_used",
            "guild_count",
            "member_count",
            "notifications_sent",
            "lastfm_api_requests",
            "html_rendered",
        ]
        if stat not in available:
            raise exceptions.Warning(f"Available stats: {', '.join(available)}")

        data = await self.bot.db.execute(
            f"""
            SELECT UNIX_TIMESTAMP(ts), DAY(ts), HOUR(ts), MINUTE(ts), {stat}
                FROM stats
                WHERE ts >= NOW() + INTERVAL -{hours} HOUR
                AND ts <  NOW() + INTERVAL 0 DAY
            ORDER BY ts
            """
        )
        datadict = {}
        for row in data:
            datadict[str(row[0])] = row[-1]

        patched_data = []
        frame = []
        now = arrow.utcnow()
        first_data_ts = arrow.get(data[0][0])
        start = now.shift(hours=-hours)
        if start < first_data_ts:
            start = first_data_ts
        for dt in arrow.Arrow.span_range("minute", start, now.shift(minutes=-1)):
            dt = dt[0]
            value = datadict.get(str(dt.timestamp), nan)
            frame.append(dt.datetime)
            patched_data.append(value)

        plotter.time_series_graph(frame, patched_data, str(discord.Color.random())),
        with open("downloads/graph.png", "rb") as img:
            await ctx.send(
                file=discord.File(img),
            )


def setup(bot):
    bot.add_cog(Information(bot))


async def get_commits(author, repository):
    url = f"https://api.github.com/repos/{author}/{repository}/commits"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    return data
