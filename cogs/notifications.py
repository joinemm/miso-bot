import discord
import asyncio
import regex
from discord.ext import commands
from modules import exceptions, util, emojis


class Notifications(commands.Cog):
    """Set keyword notifications"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "📨"
        self.keyword_regex = r"(?:^|\s|[\~\"\'\+\*\`\_\/])(\L<words>)(?:$|\W|\s|s)"
        self.notifications_cache = {}
        bot.loop.create_task(self.create_cache())

    async def create_cache(self):
        keywords = await self.bot.db.execute(
            "SELECT guild_id, user_id, keyword FROM notification",
        )
        self.notifications_cache = {}
        for guild_id, user_id, keyword in keywords:
            if self.notifications_cache.get(str(guild_id)) is None:
                self.notifications_cache[str(guild_id)] = {}

            try:
                self.notifications_cache[str(guild_id)][keyword.lower().strip()].append(
                    user_id
                )
            except KeyError:
                self.notifications_cache[str(guild_id)][keyword.lower().strip()] = [
                    user_id
                ]

    async def send_notification(self, user, message, keywords, test=False):
        content = discord.Embed(color=message.author.color)
        content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
        pattern = regex.compile(
            self.keyword_regex, words=keywords, flags=regex.IGNORECASE
        )
        highlighted_text = regex.sub(
            pattern, lambda x: f"**{x.group(0)}**", message.content
        )

        content.description = highlighted_text[:2047]
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
            if not test:
                self.bot.cache.stats_notifications_sent += 1
                for keyword in keywords:
                    await self.bot.db.execute(
                        """
                        UPDATE notification
                            SET times_triggered = times_triggered + 1
                        WHERE guild_id = %s AND user_id = %s AND keyword = %s
                        """,
                        message.guild.id,
                        user.id,
                        keyword,
                    )
        except discord.errors.Forbidden:
            self.bot.logger.warning(
                f"Forbidden when trying to send a notification to {user}"
            )

    @commands.Cog.listener()
    async def on_message(self, message):
        """Notification message handler."""
        # make sure bot cache is ready
        if not self.bot.is_ready():
            return

        # ignore DMs
        if message.guild is None:
            return

        # ignore bot messages
        if message.author.bot:
            return

        keywords = self.notifications_cache.get(str(message.guild.id), [])

        if not keywords:
            return

        pattern = regex.compile(
            self.keyword_regex, words=keywords, flags=regex.IGNORECASE
        )

        users_keywords = {}
        finds = pattern.findall(message.content)
        if not finds:
            return

        for keyword in set(finds):
            keyword = keyword.lower().strip()
            users_to_notify = keywords.get(keyword, [])
            for user_id in users_to_notify:
                if user_id == message.author.id:
                    continue

                try:
                    users_keywords[user_id].append(keyword)
                except KeyError:
                    users_keywords[user_id] = [keyword]

        for user_id, users_words in users_keywords.items():
            member = message.guild.get_member(user_id)
            if member is None or member not in message.channel.members:
                continue

            asyncio.ensure_future(self.send_notification(member, message, users_words))

    @commands.group(case_insensitive=True, aliases=["noti", "notif"])
    async def notification(self, ctx):
        """Add keyword notifications on this server."""
        await util.command_group_help(ctx)

    @notification.command()
    async def add(self, ctx, *, keyword):
        """Add a notification."""
        if ctx.guild is None:
            raise exceptions.Warning(
                "Global notifications have been removed for performance reasons."
            )

        amount = await self.bot.db.execute(
            "SELECT COUNT(*) FROM notification WHERE user_id = %s",
            ctx.author.id,
            one_value=True,
        )
        if amount and amount >= 30:
            raise exceptions.Warning(
                f"You can only have a maximum of **30** notifications. You have **{amount}**"
            )

        await ctx.message.delete()
        guild_id = ctx.guild.id
        keyword = keyword.lower().strip()

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
                f"New keyword notification for `{keyword}` set in **{ctx.guild.name}**",
            )
        except discord.errors.Forbidden:
            raise exceptions.Warning(
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
        if self.notifications_cache.get(str(guild_id)) is None:
            self.notifications_cache[str(guild_id)] = {}
        try:
            self.notifications_cache[str(guild_id)][keyword].append(ctx.author.id)
        except KeyError:
            self.notifications_cache[str(guild_id)][keyword] = [ctx.author.id]

        await util.send_success(
            ctx, f"New notification set! Check your DM {emojis.VIVISMIRK}"
        )

    @notification.command()
    async def remove(self, ctx, *, keyword):
        """Remove notification."""
        if ctx.guild is None:
            raise exceptions.Warning(
                "Please use this in the guild you want to remove notifications from."
            )

        await ctx.message.delete()
        guild_id = ctx.guild.id
        keyword = keyword.lower().strip()

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
                f"The keyword notification for `{keyword}` that you set in **{ctx.guild.name}** has been removed.",
            )
        except discord.errors.Forbidden:
            raise exceptions.Warning(
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
        await util.send_success(
            ctx, f"Removed a notification! Check your DM {emojis.VIVISMIRK}"
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

        content = discord.Embed(
            title=f":love_letter: You have {len(words)} notifications",
            color=int("dd2e44", 16),
        )

        rows = []
        for guild_id, keyword, times_triggered in sorted(words):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                guild = f"[Unknown server `{guild_id}`]"

            rows.append(
                f"**{guild}** : `{keyword}` - Triggered **{times_triggered}** times"
            )

        try:
            await util.send_as_pages(ctx.author, content, rows, maxpages=1, maxrows=50)
        except discord.errors.Forbidden:
            raise exceptions.Warning(
                "I was unable to send you a DM! Please change your settings."
            )

        if ctx.guild is not None:
            await util.send_success(
                ctx, f"Notification list sent to your DM {emojis.VIVISMIRK}"
            )

    @notification.command()
    async def clear(self, ctx):
        """
        Clears all your notifications on this server.
        Use in DMs to clear every server.
        """
        dm = ctx.guild is None
        if dm:
            await self.bot.db.execute(
                "DELETE FROM notification WHERE user_id = %s", ctx.author.id
            )
            await util.send_success(
                ctx, "Cleared all of your notifications in all servers!"
            )
        else:
            await self.bot.db.execute(
                "DELETE FROM notification WHERE user_id = %s AND guild_id = %s",
                ctx.author.id,
                ctx.guild.id,
            )
            await util.send_success(
                ctx, "Cleared all of your notifications in this server!"
            )

        # remake notification cache
        await self.create_cache()

    @notification.command()
    async def test(self, ctx, message: discord.Message = None):
        """
        Test if Miso can send you a notification.
        If supplied with a message id, will check if you would have been notified by it.
        """
        if message is None:
            try:
                await self.send_notification(
                    ctx.author, message or ctx.message, ["test"], test=True
                )
                await ctx.send(":ok_hand: Check your DM")
            except discord.errors.Forbidden:
                raise exceptions.Warning(
                    "I was unable to send you a DM! Please check your privacy settings."
                )
        else:
            if ctx.author not in message.channel.members:
                raise exceptions.Error("You cannot see this message.")

            keywords = await self.bot.db.execute(
                "SELECT keyword FROM notification WHERE user_id = %s",
                ctx.author.id,
                as_list=True,
            )

            pattern = regex.compile(
                self.keyword_regex, words=keywords, flags=regex.IGNORECASE
            )

            finds = pattern.findall(message.content)
            if not finds:
                await ctx.send(":x: This message would not notify you")
            else:
                keywords = list(set(finds))
                await self.send_notification(ctx.author, message, keywords, test=True)
                await ctx.send(":ok_hand: Check your DM")


def setup(bot):
    bot.add_cog(Notifications(bot))
