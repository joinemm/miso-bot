import discord
from discord.ext import commands
import data.database as db
import helpers.utilityfunctions as util
from helpers import emojis
import re


class Notifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        """Notification message handler."""
        # make sure bot cache is ready
        if not self.bot.is_ready:
            return

        if message.guild is None:
            return

        if message.author.bot:
            return

        keywords = db.get_keywords(message)
        if keywords is None:
            return

        for word, user_id in keywords:
            pattern = re.compile(
                r"(?:^|\s|[~*`_\/]){0}(?:$|\W)".format(re.escape(word)), flags=re.IGNORECASE
            )
            if pattern.findall(message.content):
                member = message.guild.get_member(user_id)
                if member.dm_channel is None:
                    continue
                if member is None:
                    continue
                if member not in message.channel.members:
                    continue

                # create and send notification message
                await send_notification(member, message, pattern)

    @commands.group(case_insensitive=True, aliases=["noti", "notif"])
    async def notification(self, ctx):
        """
        Add keyword notifications on this server.
        Use in DMs to manage global notifications.
        """
        await util.command_group_help(ctx)

    @notification.command()
    async def add(self, ctx, *, keyword):
        """Add a notification"""
        dm = ctx.guild is None
        if dm:
            guild_id = 0
        else:
            await ctx.message.delete()
            guild_id = ctx.guild.id

        check = db.query(
            "SELECT * FROM notifications WHERE guild_id = ? and user_id = ? and keyword = ?",
            (guild_id, ctx.author.id, keyword),
        )

        if check is not None:
            return await ctx.send(":warning: You already have this notification!")

        db.execute(
            "REPLACE INTO notifications values(?, ?, ?)",
            (guild_id, ctx.author.id, keyword),
        )
        await ctx.author.send(
            f":white_check_mark: New keyword notification `{keyword}` set "
            + ("globally" if dm else f"in `{ctx.guild.name}`")
        )
        if not dm:
            await ctx.send(
                "Set a notification!" + ("" if dm else f" Check your DMs {emojis.VIVISMIRK}")
            )

    @notification.command()
    async def remove(self, ctx, *, keyword):
        """Remove notification."""
        dm = ctx.guild is None
        if dm:
            guild_id = 0
        else:
            await ctx.message.delete()
            guild_id = ctx.guild.id

        check = db.query(
            "SELECT * FROM notifications WHERE guild_id = ? and user_id = ? and keyword = ?",
            (guild_id, ctx.author.id, keyword),
        )

        if check is None:
            return await ctx.send(":warning: You don't have that notification.")

        db.execute(
            "DELETE FROM notifications where guild_id = ? and user_id = ? and keyword = ?",
            (guild_id, ctx.author.id, keyword),
        )
        await ctx.author.send(
            f":white_check_mark: Keyword notification `{keyword}` that you set "
            + ("globally" if dm else f"in `{ctx.guild.name}`")
            + " has been removed."
        )
        if not dm:
            await ctx.send(
                "removed a notification!" + ("" if dm else f" Check your DMs {emojis.VIVISMIRK}")
            )

    @notification.command()
    async def list(self, ctx):
        """List your current notifications."""
        words = db.query(
            "SELECT guild_id, keyword FROM notifications where user_id = ? ORDER BY keyword",
            (ctx.author.id,),
        )

        if words is None:
            return await ctx.send("You have not set any notifications yet!")

        guilds = {}
        for guild_id, keyword in words:
            guilds[guild_id] = guilds.get(guild_id, []) + [keyword]

        content = discord.Embed(
            title=":love_letter: Your notifications", color=discord.Color.red()
        )
        for guild_id in guilds:
            if guild_id == 0:
                guild_name = "Global"
            else:
                server = self.bot.get_guild(guild_id)
                if server is None:
                    continue
                guild_name = server.name

            content.add_field(
                name=guild_name,
                value="\n".join(f"└`{x}`" for x in guilds.get(guild_id)),
            )

        await ctx.author.send(embed=content)
        if ctx.guild is not None:
            await ctx.send(f"Notification list sent to your DMs {emojis.VIVISMIRK}")

    @notification.command()
    async def test(self, ctx):
        await send_notification(ctx.author, ctx.message)


def setup(bot):
    bot.add_cog(Notifications(bot))


async def send_notification(user, message, pattern=None):
    content = discord.Embed(color=message.author.color)
    content.set_author(
        name=f"{message.author} | click to jump",
        icon_url=message.author.avatar_url,
        url=message.jump_url,
    )
    if pattern is None:
        highlighted_text = message.content
    else:
        highlighted_text = re.sub(pattern, lambda x: f"**{x.group(0)}**", message.content)

    content.description = highlighted_text
    content.set_footer(
        text=f"{message.guild.name} | #{message.channel.name}",
        icon_url=message.guild.icon_url,
    )
    content.timestamp = message.created_at

    try:
        await user.send(embed=content)
    except discord.errors.Forbidden:
        pass
