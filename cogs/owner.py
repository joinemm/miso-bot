import asyncio
from typing import Union

import arrow
import discord
from discord.ext import commands
from loguru import logger

from modules import util
from modules.misobot import MisoBot


class Owner(commands.Cog):
    """Bot owner only, you shouldn't be able to see this"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "👑"

    async def cog_check(self, ctx: commands.Context):
        """Check if command author is Owner"""
        return await self.bot.is_owner(ctx.author)

    @commands.command(rest_is_raw=True)
    async def say(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
        *,
        message,
    ):
        """Makes the bot say something in the given channel"""
        await ctx.send(f"Sending message to **{channel.guild}** <#{channel.id}>\n> {message}")
        await channel.send(message)

    @commands.command(rest_is_raw=True)
    async def dm(
        self,
        ctx: commands.Context,
        user: discord.User,
        *,
        message,
    ):
        """Makes the bot dm something to the given user"""
        await ctx.send(
            f"Sending message to **{user}** <@{user.id}>\n> {message}", allowed_mentions=None
        )
        await user.send(message)

    @commands.command()
    async def guilds(self, ctx: commands.Context):
        """Show all connected guilds"""
        content = discord.Embed(
            title=f"Total **{self.bot.guild_count}** guilds, **{self.bot.member_count}** members"
        )

        rows = []
        for guild in sorted(self.bot.guilds, key=lambda x: x.member_count or 0, reverse=True):
            rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def findguild(self, ctx: commands.Context, *, search_term):
        """Find a guild by name"""
        rows = []
        for guild in sorted(self.bot.guilds, key=lambda x: x.member_count or 0, reverse=True):
            if search_term.lower() in guild.name.lower():
                rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        content = discord.Embed(title=f"Found **{len(rows)}** guilds matching search term")
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def userguilds(self, ctx: commands.Context, user: discord.User):
        """Get all guilds user is part of"""
        rows = []
        for guild in sorted(self.bot.guilds, key=lambda x: x.member_count or 0, reverse=True):
            guildmember = guild.get_member(user.id)
            if guildmember is not None:
                rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        content = discord.Embed(title=f"User **{user}** found in **{len(rows)}** guilds")
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def logout(self, ctx: commands.Context):
        """Shut down the bot"""
        logger.info("LOGGING OUT")
        await ctx.send("Shutting down... :electric_plug:")
        await self.bot.close()

    @commands.command()
    async def shardreconnect(self, ctx: commands.Context, shard_id: int):
        """Disconnect and then reconnect a shard"""
        shard = self.bot.get_shard(shard_id)
        if shard is None:
            return await ctx.send(f":warning: Shard `{shard_id}` not found")

        await shard.reconnect()
        await util.send_success(ctx, f"Reconnected shard `{shard_id}`")

    @commands.group(aliases=["patron"], case_insensitive=True)
    async def donator(self, ctx: commands.Context):
        """Manage sponsors and donations"""
        await util.command_group_help(ctx)

    @donator.command(name="addsingle")
    async def donator_addsingle(
        self, ctx: commands.Context, user: discord.User, platform, amount: float, ts=None
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
        self, ctx, user: discord.User, username, platform, tier: int, amount: int, since_ts=None
    ):
        """Add a new monthly donator"""
        if since_ts is None:
            since_ts = arrow.utcnow().datetime
        else:
            since_ts = arrow.get(since_ts).datetime

        await self.bot.db.execute(
            """
            INSERT INTO donator (user_id, platform, external_username, donation_tier, donating_since, amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            user.id,
            platform,
            username,
            tier,
            since_ts,
            amount,
        )
        await util.send_success(
            ctx,
            f"Added tier {tier} ${amount} donation by **{user}** on {platform} ({username})",
        )

    @donator.command(name="remove")
    async def donator_remove(self, ctx: commands.Context, user: discord.User):
        """Remove a donator"""
        await self.bot.db.execute(
            """
            DELETE FROM donator WHERE user_id = %s
            """,
            user.id,
        )
        await util.send_success(ctx, f"Removed **{user}** from the donators list.")

    @donator.command(name="toggle")
    async def donator_toggle(self, ctx: commands.Context, user: discord.User):
        """Toggle user's donator status"""
        await self.bot.db.execute(
            """
            UPDATE donator SET currently_active = !currently_active WHERE user_id = %s
            """,
            user.id,
        )
        await util.send_success(ctx, f"**{user}** donator status changed.")

    @donator.command(name="tier")
    async def donator_tier(self, ctx: commands.Context, user: discord.User, new_tier: int):
        """Change user's donation tier"""
        await self.bot.db.execute(
            """
            UPDATE donator SET donation_tier = %s WHERE user_id = %s
            """,
            new_tier,
            user.id,
        )
        await util.send_success(ctx, f"**{user}** donation changed to **Tier {new_tier}**")

    @commands.command(name="db", aliases=["dbe", "dbq"])
    @commands.is_owner()
    async def database_query(self, ctx: commands.Context, *, statement):
        """Execute something against the local MariaDB instance"""
        changes, data = await self.bot.db.run_sql(statement)
        if changes:
            await ctx.send(f":white_check_mark: {changes} rows returned/affected")

        if not data:
            return await ctx.send("Query returned no data")
        try:
            content = "\n".join(str(r) for r in data)
            await ctx.send(f"```py\n{content}\n```")
        except discord.errors.HTTPException:
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

    @commands.group()
    async def vip(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await util.command_group_help(ctx)

    @vip.command(name="add")
    async def vip_add(self, ctx: commands.Context, user: discord.User):
        await self.bot.db.execute(
            """
            INSERT INTO vip_user VALUES(%s)
            """,
            user.id,
        )
        await util.send_success(ctx, f"{user.mention} is now VIP!")

    @vip.command(name="remove")
    async def vip_remove(self, ctx: commands.Context, user: discord.User):
        await self.bot.db.execute(
            """
            DELETE FROM vip_user WHERE user_id = %s
            """,
            user.id,
        )
        await util.send_success(ctx, f"{user.mention} is no longer VIP!")


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


async def setup(bot):
    await bot.add_cog(Owner(bot))
