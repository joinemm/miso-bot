import asyncio
from typing import Optional

import discord
import regex
from discord.ext import commands

from modules import emojis, exceptions, util
from modules.misobot import MisoBot


class Notifications(commands.Cog):
    """Set keyword notifications"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "📨"
        self.keyword_regex = r"(?:^|\s|[\~\"\'\+\*\`\_\/])(\L<words>)(?:$|\W|\s|s)"
        self.notifications_cache: dict[int, dict[str, set]] = {}

    async def cog_load(self):
        await self.create_cache()

    async def create_cache(self):
        self.notifications_cache = {}
        keywords = await self.bot.db.fetch(
            "SELECT guild_id, user_id, keyword FROM notification",
        )
        if not keywords:
            return

        for guild_id, user_id, keyword in keywords:
            if self.notifications_cache.get(guild_id) is None:
                self.notifications_cache[guild_id] = {}

            if self.notifications_cache[guild_id].get(keyword) is None:
                self.notifications_cache[guild_id][keyword] = set()

            self.notifications_cache[guild_id][keyword].add(user_id)

    async def send_notification(self, member, message, keywords, test=False):
        content = discord.Embed(color=message.author.color)
        content.set_author(name=f"{message.author}", icon_url=message.author.display_avatar.url)
        pattern = regex.compile(self.keyword_regex, words=keywords, flags=regex.IGNORECASE)
        highlighted_text = regex.sub(pattern, lambda x: f"**{x.group(0)}**", message.content)

        content.description = highlighted_text[:2047]
        content.add_field(
            name="context", value=f"[Jump to message]({message.jump_url})", inline=True
        )
        content.set_footer(
            text=f"{message.guild.name} | #{message.channel.name}",
            icon_url=getattr(message.guild.icon, "url", None),
        )
        content.timestamp = message.created_at

        try:
            await member.send(embed=content)
            self.bot.logger.info(f"Sending notification for words {keywords} to {member}")
            if not test:
                for keyword in keywords:
                    await self.bot.db.execute(
                        """
                        UPDATE notification
                            SET times_triggered = times_triggered + 1
                        WHERE guild_id = %s AND user_id = %s AND keyword = %s
                        """,
                        message.guild.id,
                        member.id,
                        keyword,
                    )
        except discord.errors.Forbidden:
            self.bot.logger.warning(f"Forbidden when trying to send a notification to {member}.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Notification message handler"""
        await self.bot.wait_until_ready()

        # ignore DMs
        if message.guild is None:
            return

        # ignore bot messages
        if message.author.bot:
            return

        keywords = self.notifications_cache.get(message.guild.id)
        if keywords is None:
            return

        pattern = regex.compile(
            self.keyword_regex,
            words=keywords.keys(),
            flags=regex.IGNORECASE,
        )

        finds = pattern.findall(message.content)
        if not finds:
            return

        users_keywords = {}
        for keyword in set(finds):
            keyword = keyword.lower().strip()
            users_to_notify = list(keywords.get(keyword) or [])
            for user_id in users_to_notify:
                if user_id == message.author.id:
                    continue

                if users_keywords.get(user_id) is None:
                    users_keywords[user_id] = set()

                users_keywords[user_id].add(keyword)

        for user_id, users_words in users_keywords.items():
            try:
                member = await message.guild.fetch_member(user_id)
            except discord.NotFound:
                self.bot.logger.warning(
                    f"User {user_id} not found, deleting their notification for {users_words}"
                )
                await self.bot.db.execute(
                    """DELETE FROM notification WHERE guild_id = %s AND user_id = %s AND keyword IN %s""",
                    message.guild.id,
                    user_id,
                    users_words,
                )
                await self.create_cache()
                continue

            if member is not None and message.channel.permissions_for(member).read_messages:
                asyncio.ensure_future(self.send_notification(member, message, users_words))

    @commands.group(case_insensitive=True, aliases=["noti", "notif"])
    async def notification(self, ctx: commands.Context):
        """Manage your keyword notifications on this server"""
        await util.command_group_help(ctx)

    @notification.command(name="add")
    async def notification_add(self, ctx: commands.Context, *, keyword):
        """Add a notification keyword"""
        if ctx.guild is None:
            raise exceptions.CommandWarning(
                "Global notifications have been removed for performance reasons."
            )

        amount = await self.bot.db.fetch_value(
            "SELECT COUNT(*) FROM notification WHERE user_id = %s",
            ctx.author.id,
        )
        if amount and amount >= 30:
            raise exceptions.CommandWarning(
                f"You can only have a maximum of **30** notifications. You have **{amount}**"
            )

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        guild_id = ctx.guild.id
        keyword = keyword.lower().strip()

        check = await self.bot.db.fetch(
            """
            SELECT * FROM notification WHERE guild_id = %s AND user_id = %s AND keyword = %s
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )
        if check:
            raise exceptions.CommandWarning("You already have this notification!")

        try:
            await util.send_success(
                ctx.author,
                f"New keyword notification for `{keyword}` set in **{ctx.guild.name}**",
            )
        except discord.errors.Forbidden:
            raise exceptions.CommandWarning(
                "I was unable to send you a DM! Please change your settings."
            )

        await self.bot.db.execute(
            """
            INSERT INTO notification (guild_id, user_id, keyword)
                VALUES (%s, %s, %s)
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )

        # remake notification cache
        await self.create_cache()
        await util.send_success(ctx, f"New notification set! Check your DM {emojis.VIVISMIRK}")

    @notification.command(name="remove")
    async def notification_remove(self, ctx: commands.Context, *, keyword):
        """Remove a notification keyword"""
        if ctx.guild is None:
            raise exceptions.CommandWarning(
                "Please use this in the guild you want to remove notifications from."
            )

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        guild_id = ctx.guild.id
        keyword = keyword.lower().strip()

        check = await self.bot.db.fetch(
            """
            SELECT * FROM notification WHERE guild_id = %s AND user_id = %s AND keyword = %s
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )
        if not check:
            raise exceptions.CommandWarning("You don't have such notification!")

        try:
            await util.send_success(
                ctx.author,
                f"The keyword notification for `{keyword}` that you set in **{ctx.guild.name}** has been removed.",
            )
        except discord.errors.Forbidden:
            raise exceptions.CommandWarning(
                "I was unable to send you a DM! Please change your settings."
            )

        await self.bot.db.execute(
            """
            DELETE FROM notification WHERE guild_id = %s AND user_id = %s AND keyword = %s
            """,
            guild_id,
            ctx.author.id,
            keyword,
        )

        # remake notification cache
        await self.create_cache()
        await util.send_success(ctx, f"Removed a notification! Check your DM {emojis.VIVISMIRK}")

    @notification.command(name="list")
    async def notification_list(self, ctx: commands.Context):
        """List your current notifications"""
        words = await self.bot.db.fetch(
            """
            SELECT guild_id, keyword, times_triggered FROM notification WHERE user_id = %s ORDER BY keyword
            """,
            ctx.author.id,
        )

        if not words:
            raise exceptions.CommandInfo("You have not set any notifications yet!")

        content = discord.Embed(
            title=f":love_letter: You have {len(words)} notifications",
            color=int("dd2e44", 16),
        )

        rows = []
        for guild_id, keyword, times_triggered in sorted(words):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                guild = f"[Unknown server `{guild_id}`]"

            rows.append(f"**{guild}** : `{keyword}` - Triggered **{times_triggered}** times")

        try:
            await util.send_as_pages(ctx.author, content, rows, maxpages=1, maxrows=50)
        except discord.errors.Forbidden:
            raise exceptions.CommandWarning(
                "I was unable to send you a DM! Please change your settings."
            )

        if ctx.guild is not None:
            await util.send_success(ctx, f"Notification list sent to your DM {emojis.VIVISMIRK}")

    @notification.command(name="clear")
    async def notification_clear(self, ctx: commands.Context):
        """
        Clears all your notifications on this server
        Use in DMs to clear every server.
        """
        if ctx.guild is None:
            await self.bot.db.execute(
                """
                DELETE FROM notification WHERE user_id = %s
                """,
                ctx.author.id,
            )
            await util.send_success(ctx, "Cleared all of your notifications in all servers!")
        else:
            await self.bot.db.execute(
                """
                DELETE FROM notification WHERE user_id = %s AND guild_id = %s
                """,
                ctx.author.id,
                ctx.guild.id,
            )
            await util.send_success(ctx, "Cleared all of your notifications in this server!")

        # remake notification cache
        await self.create_cache()

    @notification.command(name="test")
    async def notification_test(
        self, ctx: commands.Context, message: Optional[discord.Message] = None
    ):
        """
        Test if Miso can send you a notification
        If supplied with a message id, will check if you would have been notified by it.
        """
        if message is None:
            try:
                await self.send_notification(
                    ctx.author, message or ctx.message, ["test"], test=True
                )
                await ctx.send(":ok_hand: Check your DM")
            except discord.errors.Forbidden:
                raise exceptions.CommandWarning(
                    "I was unable to send you a DM! Please check your privacy settings."
                )
        else:
            if (
                isinstance(message.channel, (discord.abc.GuildChannel))
                and ctx.author not in message.channel.members
            ):
                raise exceptions.CommandError("You cannot see this message.")

            keywords = await self.bot.db.fetch_flattened(
                "SELECT keyword FROM notification WHERE user_id = %s",
                ctx.author.id,
            )

            pattern = regex.compile(self.keyword_regex, words=keywords, flags=regex.IGNORECASE)

            finds = pattern.findall(message.content)
            if not finds:
                await ctx.send(":x: This message would not notify you")
            else:
                keywords = list(set(finds))
                await self.send_notification(ctx.author, message, keywords, test=True)
                await ctx.send(":ok_hand: Check your DM")


async def setup(bot):
    await bot.add_cog(Notifications(bot))
