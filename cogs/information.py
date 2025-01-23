# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import copy
import time
from typing import Optional

import arrow
import discord
import humanize
import orjson
from discord.ext import commands

from modules import emojis, exceptions, util
from modules.misobot import MisoBot
from modules.ui import RowPaginator


class Information(commands.Cog):
    """See bot related information"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "ℹ️"

    @commands.command()
    async def invite(self, ctx: commands.Context):
        """Invite Miso to your server!"""
        if not self.bot.user:
            raise exceptions.CommandError("Not logged in! This shouldn't happen...")
        url = discord.utils.oauth_url(
            self.bot.user.id, permissions=discord.Permissions(1515318537286)
        )
        content = discord.Embed(title="Invite me to your server!")
        content.set_thumbnail(url=self.bot.user.display_avatar.url)
        content.description = f"[Click here]({url})"
        await ctx.send(embed=content)

    @commands.command()
    async def github(self, ctx: commands.Context):
        """See the bot's source code"""
        await ctx.send("https://github.com/joinemm/miso-bot")

    @commands.command(aliases=["patreon", "kofi", "sponsor", "ko-fi"])
    async def donate(self, ctx: commands.Context):
        """Donate to keep the bot running!"""
        content = discord.Embed(
            title="Consider donating to help keep Miso Bot online!",
            colour=discord.Colour.orange(),
        )
        content.add_field(
            name="Github Sponsors",
            value="https://github.com/sponsors/joinemm",
            inline=False,
        )
        content.add_field(
            name="Ko-Fi",
            value="https://ko-fi.com/joinemm",
            inline=False,
        )
        content.add_field(
            name="Patreon (high fees so not recommended)",
            value="https://www.patreon.com/joinemm",
            inline=False,
        )
        content.add_field(
            name="Litecoin wallet address",
            value="`ltc1qsxmy8q8ptdlhdcamypa2uspj8zf8m0ukua9vn5`",
            inline=False,
        )
        content.set_footer(
            text="Donations will be used to pay for server and upkeep costs"
        )
        await ctx.send(embed=content)

    @commands.command(aliases=["patrons", "supporters", "sponsors"])
    async def donators(self, ctx: commands.Context):
        """See who has donated!"""
        patrons = await self.bot.db.fetch_flattened(
            """
            SELECT user_id FROM donator
            """
        )

        donators = []
        if patrons:
            for user_id in patrons:
                user = self.bot.get_user(user_id)
                if user is None:
                    user = self.bot.donator_cache.get(user_id, 0)
                    if user == 0:
                        user = await self.bot.fetch_user(user_id)
                        if user is None or user.name.startswith("Deleted User "):
                            self.bot.donator_cache[user_id] = None
                            continue
                        self.bot.donator_cache[user_id] = user

                if user:
                    donators.append(f"**{user}**")

        n = 20
        chunks = [
            donators[i * n : (i + 1) * n] for i in range((len(donators) + n - 1) // n)
        ]

        if not donators:
            raise exceptions.CommandInfo(
                "There are no donators :thinking: Maybe you should be the first one"
            )

        description = " | ".join(
            [
                "[github](https://github.com/sponsors/joinemm)",
                "[ko-fi](https://ko-fi.com/joinemm)",
                "[patreon](https://patreon.com/joinemm)",
            ]
        )

        content = discord.Embed(
            title=":heart: Miso Bot donators",
            color=int("dd2e44", 16),
            description=description,
        )
        for chunk in chunks:
            content.add_field(name="───── ⋆⋅☆⋅⋆ ─────", value="\n".join(chunk))

        await ctx.send(embed=content)

    @commands.command(name="info")
    async def info(self, ctx: commands.Context):
        """Get information about the bot"""
        if not self.bot.user or not self.bot.owner_id:
            raise exceptions.CommandError("Not logged in! This shouldn't happen...")

        content = discord.Embed(
            title=f"Miso Bot | version {self.bot.version}",
            colour=int("E46A92", 16),
        )
        owner = await self.bot.fetch_user(self.bot.owner_id)
        content.description = (
            f"Created by **{owner}** {owner.mention} \n"
            f"using *discord.py* {discord.__version__}\n\n"
            f"Use `{ctx.prefix}help` to get help on any commands, \n"
            f"or visit the website for more detailed instructions.\n\n"
            f"Currently in **{self.bot.guild_count}** servers "
            f"with a total member count of **{self.bot.member_count}**."
        )
        content.set_thumbnail(url=self.bot.user.display_avatar.url)
        content.add_field(name="Website", value="https://misobot.xyz", inline=False)
        content.add_field(
            name="Github", value="https://github.com/joinemm/miso-bot", inline=False
        )
        content.add_field(
            name="Discord", value="https://discord.gg/RzDW3Ne", inline=False
        )

        data = await self.get_commits("joinemm", "miso-bot")
        last_update = data[0]["commit"]["author"].get("date")
        content.set_footer(text=f"Latest update: {arrow.get(last_update).humanize()}")

        await ctx.send(embed=content)

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """Get the bot's ping"""
        test_message = await ctx.send(":ping_pong:")
        cmd_lat = (
            test_message.created_at - ctx.message.created_at
        ).total_seconds() * 1000
        discord_lat = self.bot.latency * 1000
        content = discord.Embed(
            colour=discord.Color.red(),
            description=f"**Command response** `{cmd_lat}` ms\n"
            f"**Discord API latency** `{discord_lat:.1f}` ms",
        )
        await test_message.edit(content="", embed=content)

    @commands.command(aliases=["shards"])
    async def shardinfo(self, ctx: commands.Context):
        """Get information about the current shards"""
        content = discord.Embed(title=f"Running {len(self.bot.shards)} shards")
        shards = []
        for shard in self.bot.shards.values():
            emoji = (
                emojis.Status["offline"]
                if shard.is_closed()
                else emojis.Status["online"]
            )
            shards.append(
                f"{emoji.value} **Shard `{shard.id}`** - `{shard.latency * 1000:.2f}` ms"
                + (
                    " :point_left:"
                    if ctx.guild and ctx.guild.shard_id == shard.id
                    else ""
                )
            )

        content.description = "\n".join(shards)
        await ctx.send(embed=content)

    @commands.command()
    async def metrics(self, ctx: commands.Context):
        """Show some internal bot metrics"""
        content = discord.Embed(
            title="Metrics",
            colour=int("E46A92", 16),
        )
        content.timestamp = arrow.now().datetime
        uptime = time.time() - self.bot.start_time
        prom = self.bot.get_cog("Prometheus")

        content.description = "\n".join(
            [
                f"**Ping**: `{int(prom.ping._value.get() * 1000)}ms`",
                f"**Uptime**: {humanize.naturaldelta(uptime)}",
                f"**Loading time**: {humanize.naturaldelta(self.bot.boot_up_time)}",
                f"**Users total**: `{int(prom.users_total._value.get())}`",
                f"**Users cached**: `{int(prom.users_cached._value.get())}`",
                f"**Guilds total**: `{int(prom.guilds_total._value.get())}`",
                f"**Guilds cached**: `{int(prom.guilds_cached._value.get())}`",
                f"**Median member count**: `{int(prom.median_member_count._value.get())}`",
            ]
        )

        await ctx.send(embed=content)

    @commands.command()
    async def changelog(self, ctx: commands.Context, author="joinemm", repo="miso-bot"):
        """See github commit history"""
        data = await self.get_commits(author, repo)
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
    async def roleinfo(self, ctx: commands.Context, *, role: discord.Role):
        """Get information about a role"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        content = discord.Embed(title=f"@{role.name} | #{role.id}")

        content.colour = role.color
        member_count = len(role.members)
        percentage = (
            int(member_count / ctx.guild.member_count * 100)
            if ctx.guild.member_count
            else None
        )

        if isinstance(role.icon, discord.Asset):
            content.set_thumbnail(url=role.icon.url)
        elif isinstance(role.icon, str):
            content.title = f"{role.icon} @{role.name} | #{role.id}"

        content.add_field(name="Color", value=str(role.color).upper())
        content.add_field(
            name="Member count",
            value=(
                f"{member_count} / {ctx.guild.member_count} ({percentage}%)"
                if ctx.guild.member_count
                else member_count
            ),
        )
        content.add_field(
            name="Created at", value=role.created_at.strftime("%d/%m/%Y %H:%M")
        )
        content.add_field(name="Hoisted", value=str(role.hoist))
        content.add_field(name="Mentionable", value=role.mentionable)
        content.add_field(name="Mention", value=role.mention)
        if role.managed and role.tags:
            if role.tags.is_bot_managed() and role.tags.bot_id:
                manager = ctx.guild.get_member(role.tags.bot_id)
            elif role.tags.is_integration() and role.tags.integration_id:
                manager = ctx.guild.get_member(role.tags.integration_id)
            elif role.tags.is_premium_subscriber():
                manager = "Server boosting"
            else:
                manager = "UNKNOWN"
            content.add_field(name="Managed by", value=manager)

        if perms := [
            f"`{perm.upper()}`" for perm, allow in iter(role.permissions) if allow
        ]:
            content.add_field(
                name="Allowed permissions", value=" ".join(perms), inline=False
            )

        await ctx.send(embed=content)

    @commands.group(usage="[command]", case_insensitive=True)
    async def commandstats(self, ctx: commands.Context):
        """See command usage statistics"""
        if ctx.invoked_subcommand is None:
            if args := ctx.message.content.split()[1:]:
                await self.commandstats_single(ctx, " ".join(args))
            else:
                await util.send_command_help(ctx)

    @commandstats.command(name="server")
    async def commandstats_server(
        self, ctx: commands.Context, user: Optional[discord.Member] = None
    ):
        """Most used commands in this server"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        content = discord.Embed(
            title=f":bar_chart: Most used commands in {ctx.guild.name}"
            + ("" if user is None else f" by {user}")
        )
        opt = [user.id] if user is not None else []
        data = await self.bot.db.fetch(
            f"""
            SELECT command_name, SUM(use_sum) as total FROM (
                SELECT command_name, SUM(uses) as use_sum, user_id FROM command_usage
                    WHERE command_type = 'internal'
                      AND guild_id = %s
                    {"AND user_id = %s" if user is not None else ""}
                GROUP BY command_name, user_id
            ) as subq
            GROUP BY command_name
            ORDER BY total DESC
            """,
            ctx.guild.id,
            *opt,
        )
        if not data:
            raise exceptions.CommandWarning("No commands have been used yet!")

        rows = []
        total = 0
        for i, (command_name, count) in enumerate(data, start=1):
            total += count
            rows.append(
                f"`#{i:2}` **{count}** use{'' if count == 1 else 's'} : "
                f"`{ctx.prefix}{command_name}`"
            )

        if rows:
            content.set_footer(text=f"Total {total} commands")
            await RowPaginator(content, rows).run(ctx)
        else:
            content.description = "No data :("
            await ctx.send(embed=content)

    @commandstats.command(name="global")
    @commands.cooldown(1, 180)
    @commands.is_owner()
    async def commandstats_global(
        self, ctx: commands.Context, user: Optional[discord.Member] = None
    ):
        """Most used commands globally"""
        content = discord.Embed(
            title=":bar_chart: Most used commands"
            + ("" if user is None else f" by {user}")
        )
        opt = [user.id] if user is not None else []
        data = await self.bot.db.fetch(
            f"""
            SELECT command_name, SUM(use_sum) as total FROM (
                SELECT command_name, SUM(uses) as use_sum, user_id FROM command_usage
                    WHERE command_type = 'internal'
                    {"AND user_id = %s" if user is not None else ""}
                GROUP BY command_name, user_id
            ) as subq
            GROUP BY command_name
            ORDER BY total DESC
            """,
            *opt,
        )
        if not data:
            raise exceptions.CommandWarning("No commands have been used yet!")

        rows = []
        total = 0
        for i, (command_name, count) in enumerate(data, start=1):
            total += count
            rows.append(
                f"`#{i:2}` **{count}** use{'' if count == 1 else 's'} : "
                f"`{ctx.prefix}{command_name}`"
            )

        if rows:
            content.set_footer(text=f"Total {total} commands")
            await RowPaginator(content, rows).run(ctx)
        else:
            content.description = "No data :("
            await ctx.send(embed=content)

    async def commandstats_single(self, ctx: commands.Context, command_name):
        """Stats of a single command"""
        command = self.bot.get_command(command_name)
        if command is None:
            raise exceptions.CommandInfo(
                f"Command `{ctx.prefix}{command_name}` does not exist!"
            )

        content = discord.Embed(
            title=f":bar_chart: `{ctx.prefix}{command.qualified_name}`"
        )

        # set command name to be tuple of subcommands if this is a command group
        group = hasattr(command, "commands")
        if group:
            command_name = tuple(
                [f"{command.name} {x.name}" for x in command.commands] + [command_name]
            )
        else:
            command_name = command.qualified_name

        total_uses: int = 0
        most_used_by_user_id: Optional[int] = None
        most_used_by_user_amount: int = 0
        most_used_by_guild_amount: int = 0
        most_used_by_guild_id: Optional[int] = None

        global_use_data = await self.bot.db.fetch_row(
            f"""
            SELECT SUM(use_sum) as total, user_id, MAX(use_sum) FROM (
                SELECT SUM(uses) as use_sum, user_id FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name {"IN %s" if group else "= %s"}
                GROUP BY user_id
            ) as subq
            """,
            command_name,
        )
        if global_use_data:
            total_uses, most_used_by_user_id, most_used_by_user_amount = global_use_data

        content.add_field(name="Uses", value=total_uses)

        uses_by_guild_data = await self.bot.db.fetch_row(
            f"""
            SELECT guild_id, MAX(use_sum) FROM (
                SELECT guild_id, SUM(uses) as use_sum FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name {"IN %s" if group else "= %s"}
                GROUP BY guild_id
            ) as subq
            """,
            command_name,
        )
        if uses_by_guild_data:
            most_used_by_guild_id, most_used_by_guild_amount = uses_by_guild_data

        if ctx.guild:
            uses_in_this_server = (
                await self.bot.db.fetch_value(
                    f"""
                    SELECT SUM(uses) FROM command_usage
                        WHERE command_type = 'internal'
                        AND command_name {"IN %s" if group else "= %s"}
                        AND guild_id = %s
                    GROUP BY guild_id
                    """,
                    command_name,
                    ctx.guild.id,
                )
                or 0
            )
            content.add_field(name="on this server", value=uses_in_this_server)

        # show the data in embed fields
        if most_used_by_guild_id:
            content.add_field(
                name="Server most used in",
                value=f"{self.bot.get_guild(most_used_by_guild_id)} ({most_used_by_guild_amount})",
                inline=False,
            )

        if most_used_by_user_id:
            content.add_field(
                name="Most total uses by",
                value=f"{self.bot.get_user(most_used_by_user_id)} ({most_used_by_user_amount})",
            )

        # additional data for command groups
        if group:
            content.description = "Command Group"
            subcommands_tuple = tuple(
                f"{command.name} {x.name}" for x in command.commands
            )
            subcommand_usage = await self.bot.db.fetch(
                """
                SELECT command_name, SUM(uses) FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name IN %s
                GROUP BY command_name ORDER BY SUM(uses) DESC
                """,
                subcommands_tuple,
            )
            if subcommand_usage:
                content.add_field(
                    name="Subcommand usage",
                    value="\n".join(f"{s[0]} - **{s[1]}**" for s in subcommand_usage),
                    inline=False,
                )

        await ctx.send(embed=content)

    @commands.command(aliases=["serverdp", "sdp", "guildicon"])
    async def servericon(self, ctx: commands.Context, guild_id: Optional[int] = None):
        """Get the icon of the server"""
        guild = self.bot.get_guild(guild_id) if guild_id else ctx.guild
        if guild is None:
            raise exceptions.CommandError("Can't get guild")

        if guild.icon is None:
            raise exceptions.CommandWarning("This server has no icon.")

        content = discord.Embed()
        content.set_author(name=str(guild), url=guild.icon.url)
        content.set_image(url=guild.icon.url)
        stats = await util.image_info_from_url(self.bot.session, guild.icon.url)
        color = await util.color_from_image_url(
            self.bot.session, str(guild.icon.replace(size=64, format="png"))
        )
        content.colour = int(str(color), 16)
        if stats:
            content.set_footer(
                text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
            )

        await ctx.send(embed=content)

    async def get_commits(self, author, repository):
        url = f"https://api.github.com/repos/{author}/{repository}/commits"
        async with self.bot.session.get(url) as response:
            data = await response.json(loads=orjson.loads)

        return data


async def setup(bot):
    await bot.add_cog(Information(bot))
