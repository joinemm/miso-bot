import asyncio

import arrow
import nextcord
from nextcord.ext import commands

from modules import log, util

logger = log.get_logger(__name__)


class Owner(commands.Cog):
    """Bot owner only, you shouldn't be able to see this"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "👑"

    async def cog_check(self, ctx: commands.Context):
        """Check if command author is Owner"""
        return await self.bot.is_owner(ctx.author)

    @commands.command(rest_is_raw=True)
    async def say(self, ctx: commands.Context, channel_id: int, *, message):
        """Make the bot say something in a given channel"""
        channel = self.bot.get_channel(channel_id)
        guild = channel.guild

        await ctx.send(f"Sending message to **{guild}** <#{channel.id}>\n> {message}")
        await channel.send(message)

    @commands.command()
    async def guilds(self, ctx: commands.Context):
        """Show all connected guilds"""
        membercount = len(set(self.bot.get_all_members()))
        content = nextcord.Embed(
            title=f"Total **{len(self.bot.guilds)}** guilds, **{membercount}** unique users"
        )

        rows = []
        for guild in sorted(self.bot.guilds, key=lambda x: x.member_count, reverse=True):
            rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def findguild(self, ctx: commands.Context, *, search_term):
        """Find a guild by name"""
        rows = []
        for guild in sorted(self.bot.guilds, key=lambda x: x.member_count, reverse=True):
            if search_term.lower() in guild.name.lower():
                rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        content = nextcord.Embed(title=f"Found **{len(rows)}** guilds matching search term")
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def userguilds(self, ctx: commands.Context, user: nextcord.User):
        """Get all guilds user is part of"""
        rows = []
        for guild in sorted(self.bot.guilds, key=lambda x: x.member_count, reverse=True):
            guildmember = guild.get_member(user.id)
            if guildmember is not None:
                rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        content = nextcord.Embed(title=f"User **{user}** found in **{len(rows)}** guilds")
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def logout(self, ctx: commands.Context):
        """Shut down the bot"""
        print("LOGGING OUT")
        await ctx.send("Shutting down... :electric_plug:")
        await self.bot.close()

    @commands.group(aliases=["patron"], case_insensitive=True)
    async def donator(self, ctx: commands.Context):
        """Manage sponsors and donations"""
        await util.command_group_help(ctx)

    @donator.command(name="addsingle")
    async def donator_addsingle(
        self, ctx: commands.Context, user: nextcord.User, platform, amount: float, ts=None
    ):
        """Add a new single time donation"""
        if ts is None:
            ts = arrow.utcnow().datetime
        else:
            ts = arrow.get(ts).datetime

        await self.bot.db.execute(
            "INSERT INTO donation (user_id, platform, amount, donated_on) VALUES (%s, %s, %s, %s)",
            user.id,
            platform,
            amount,
            ts,
        )
        await util.send_success(
            ctx,
            f"New donation of **${amount}** by **{user}** added",
        )

    @donator.command(name="add")
    async def donator_add(
        self, ctx, user: nextcord.User, username, platform, tier: int, since_ts=None
    ):
        """Add a new monthly donator"""
        if since_ts is None:
            since_ts = arrow.utcnow().datetime
        else:
            since_ts = arrow.get(since_ts).datetime

        await self.bot.db.execute(
            "INSERT INTO donator (user_id, platform, external_username, donation_tier, donating_since) VALUES (%s, %s, %s, %s, %s)",
            user.id,
            platform,
            username,
            tier,
            since_ts,
        )
        await util.send_success(
            ctx,
            f"**{user}** is now a **Tier {tier}** donator on **{platform}** as *{username}*",
        )

    @donator.command(name="remove")
    async def donator_remove(self, ctx: commands.Context, user: nextcord.User):
        """Remove a donator"""
        await self.bot.db.execute("DELETE FROM donator WHERE user_id = %s", user.id)
        await util.send_success(ctx, f"Removed **{user}** from the donators list.")

    @donator.command(name="toggle")
    async def donator_toggle(self, ctx: commands.Context, user: nextcord.User):
        """Toggle user's donator status"""
        await self.bot.db.execute(
            "UPDATE donator SET currently_active = !currently_active WHERE user_id = %s",
            user.id,
        )
        await util.send_success(ctx, f"**{user}** donator status changed.")

    @donator.command(name="tier")
    async def donator_tier(self, ctx: commands.Context, user: nextcord.User, new_tier: int):
        """Change user's donation tier"""
        await self.bot.db.execute(
            "UPDATE donator SET donation_tier = %s WHERE user_id = %s",
            new_tier,
            user.id,
        )
        await util.send_success(ctx, f"**{user}** donation changed to **Tier {new_tier}**")

    @commands.command(name="db", aliases=["dbe", "dbq"])
    @commands.is_owner()
    async def database_query(self, ctx: commands.Context, *, statement):
        """Execute something against the local MariaDB instance"""
        data = await self.bot.db.execute(statement)
        try:
            if data:
                content = "\n".join(str(r) for r in data)
                await ctx.send(f"```py\n{content}\n```")
            else:
                await ctx.send(":white_check_mark:")
        except nextcord.errors.HTTPException:
            # too long, page it
            pages = []
            this_page = "```py\n"
            for row in data:
                if len(this_page + "\n" + str(row)) < 1993:
                    this_page += "\n" + str(row)
                else:
                    this_page += "\n```"
                    pages.append(this_page)
                    this_page = "```py\n"

            page_iterator = util.TwoWayIterator(pages)
            msg = await ctx.send(page_iterator.current())

            async def switch_page(new_page):
                await msg.edit(content=new_page)

            async def previous_page():
                content = page_iterator.previous()
                if content is not None:
                    await switch_page(content)

            async def next_page():
                content = page_iterator.next()
                if content is not None:
                    await switch_page(content)

            functions = {"⬅": previous_page, "➡": next_page}
            asyncio.ensure_future(util.reaction_buttons(ctx, msg, functions))

    @commands.command(aliases=["fmban"])
    async def fmflag(self, ctx: commands.Context, lastfm_username, *, reason):
        """Flag LastFM account as a cheater"""
        await self.bot.db.execute(
            "INSERT INTO lastfm_cheater VALUES(%s, %s, %s)",
            lastfm_username.lower(),
            arrow.utcnow().datetime,
            reason,
        )
        await util.send_success(ctx, f"Flagged LastFM profile `{lastfm_username}` as a cheater.")

    @commands.command(aliases=["fmunban"])
    async def fmunflag(self, ctx: commands.Context, lastfm_username):
        """Remove cheater flag from an LastFM account"""
        await self.bot.db.execute(
            "DELETE FROM lastfm_cheater WHERE lastfm_username = %s",
            lastfm_username.lower(),
        )
        await util.send_success(ctx, f"`{lastfm_username}` is no longer flagged as a cheater.")


def clean_codeblock(text):
    """Remove codeblocks and empty lines, return lines"""
    text = text.strip(" `")
    lines = text.split("\n")
    clean_lines = []

    if lines[0] in ["py", "python"]:
        lines = lines[1:]

    for line in lines:
        if line.strip() != "":
            clean_lines.append(line)

    return clean_lines


def setup(bot):
    bot.add_cog(Owner(bot))
