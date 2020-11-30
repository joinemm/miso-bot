import discord
from discord.ext import commands
import helpers.utilityfunctions as util
from helpers import emojis
import re
from helpers import exceptions


class Notifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_notification(self, user, message, pattern=None):
        content = discord.Embed(color=message.author.color)
        content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
        if pattern is None:
            highlighted_text = message.content
        else:
            highlighted_text = re.sub(pattern, lambda x: f"**{x.group(0)}**", message.content)

        content.description = highlighted_text
        content.add_field(
            name="context", value=f"[Jump to message]({message.jump_url})", inline=True
        )
        content.set_footer(
            text=f"{message.guild.name} | #{message.channel.name}",
            icon_url=message.guild.icon_url,
        )
        content.timestamp = message.created_at

        try:
            await user.send(embed=content)
        except discord.errors.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Notification message handler."""
        # make sure bot cache is ready
        if not self.bot.is_ready:
            return

        # ignore DMs
        if message.guild is None:
            return

        # ignore bot messages
        if message.author.bot:
            return

        # select all keywords applicable to this server, and also global keywords (guild_id=0)
        keywords = await self.bot.db.execute(
            """
            SELECT guild_id, user_id, keyword FROM notification
                WHERE (guild_id = %s OR guild_id = 0)
                  AND user_id != %s
            """,
            message.guild.id,
            message.author.id,
        )

        if not keywords:
            return

        for guild_id, user_id, keyword in keywords:
            member = message.guild.get_member(user_id)
            if member is None or member not in message.channel.members:
                continue

            pattern = re.compile(
                r"(?:^|\s|[~*`_\/]){0}(?:$|\W)".format(re.escape(keyword)), flags=re.IGNORECASE
            )
            if pattern.findall(message.content):
                await self.send_notification(member, message, pattern)
                await self.bot.db.execute(
                    """
                    UPDATE notification
                        SET times_triggered = times_triggered + 1
                    WHERE guild_id = %s AND user_id = %s AND keyword = %s
                    """,
                    guild_id,
                    user_id,
                    keyword,
                )

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

        check = await self.bot.db.execute(
            """
            SELECT * FROM notification WHERE guild_id = %s AND user_id = %s AND keyword = %s
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )
        if check:
            raise exceptions.Warning("You already have this notification!")

        try:
            await util.send_success(
                ctx.author,
                f'New keyword notification for `"{keyword}"` set '
                + ("globally" if dm else f"in **{ctx.guild.name}**"),
            )
        except discord.errors.Forbidden:
            raise exceptions.Warning("I was unable to send you a DM. Please change your settings.")

        await self.bot.db.execute(
            """
            INSERT INTO notification (guild_id, user_id, keyword)
                VALUES (%s, %s, %s)
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )

        if not dm:
            await util.send_success(
                ctx,
                "Succesfully set a new notification!"
                + ("" if dm else f" Check your DM {emojis.VIVISMIRK}"),
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

        check = await self.bot.db.execute(
            """
            SELECT * FROM notification WHERE guild_id = %s AND user_id = %s AND keyword = %s
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )
        if not check:
            raise exceptions.Warning("You don't have such notification!")

        try:
            await util.send_success(
                ctx.author,
                f'The keyword notification for `"{keyword}"` that you set '
                + ("globally" if dm else f"in **{ctx.guild.name}**")
                + " has been removed.",
            )
        except discord.errors.Forbidden:
            raise exceptions.Warning("I was unable to send you a DM. Please change your settings.")

        await self.bot.db.execute(
            """
            DELETE FROM notification WHERE guild_id = %s AND user_id = %s AND keyword = %s
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )

        if not dm:
            await util.send_success(
                ctx,
                "Succesfully removed a notification!"
                + ("" if dm else f" Check your DM {emojis.VIVISMIRK}"),
            )

    @notification.command()
    async def list(self, ctx):
        """List your current notifications."""
        words = await self.bot.db.execute(
            """
            SELECT guild_id, keyword, times_triggered FROM notification WHERE user_id = %s ORDER BY keyword
            """,
            ctx.author.id,
        )

        if not words:
            raise exceptions.Info("You have not set any notifications yet!")

        content = discord.Embed(title=":love_letter: Your notifications", color=int("dd2e44", 16))

        rows = []
        for guild_id, keyword, times_triggered in words:
            guild = self.bot.get_guild(guild_id)
            rows.append(f'`"{keyword}"` in *{guild}* - triggered **{times_triggered}** times')

        try:
            await util.send_as_pages(ctx.author, content, rows)
        except discord.errors.Forbidden:
            raise exceptions.Warning("I was unable to send you a DM. Please change your settings.")

        if ctx.guild is not None:
            await ctx.send(f"Notification list sent to your DM {emojis.VIVISMIRK}")

    @notification.command()
    async def test(self, ctx):
        """Test if Miso can send you a notification."""
        try:
            await self.send_notification(ctx.author, ctx.message)
            await ctx.send(":ok_hand:")
        except discord.errors.Forbidden:
            raise exceptions.Warning("I was unable to send you a DM. Please change your settings.")


def setup(bot):
    bot.add_cog(Notifications(bot))
