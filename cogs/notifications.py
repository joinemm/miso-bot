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
        self.notifications_cache = {}
        self.global_notifications_cache = {}
        bot.loop.create_task(self.create_cache())

    async def create_cache(self):
        self.notifications_cache = {}
        self.global_notifications_cache = {}
        keywords = await self.bot.db.execute(
            "SELECT guild_id, user_id, keyword FROM notification",
        )
        for guild_id, user_id, keyword in keywords:
            if guild_id == 0:
                try:
                    self.global_notifications_cache[keyword].append(user_id)
                except KeyError:
                    self.global_notifications_cache[keyword] = [user_id]
            else:
                if self.notifications_cache.get(str(guild_id)) is None:
                    self.notifications_cache[str(guild_id)] = {}
                try:
                    self.notifications_cache[str(guild_id)][keyword].append(user_id)
                except KeyError:
                    self.notifications_cache[str(guild_id)][keyword] = [user_id]

    async def send_notification(self, user, message, keyword, test=False):
        content = discord.Embed(color=message.author.color)
        content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
        pattern = regex.compile(
            r"(?:^|\s|[~*`_\/])({0})(?:$|\W)".format(regex.escape(keyword)), flags=regex.IGNORECASE
        )
        highlighted_text = regex.sub(pattern, lambda x: f"**{x.group(0)}**", message.content)

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
            pass

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

        # select all keywords applicable to this server, and also global keywords (guild_id=0)

        keywords = {}
        for kw in self.global_notifications_cache:
            for v in self.global_notifications_cache[kw]:
                try:
                    keywords[kw.lower()].append(v)
                except KeyError:
                    keywords[kw.lower()] = [v]

        guild_keywords = self.notifications_cache.get(str(message.guild.id))
        if guild_keywords is not None:
            for kw in guild_keywords.keys():
                for v in guild_keywords[kw]:
                    try:
                        keywords[kw.lower()].append(v)
                    except KeyError:
                        keywords[kw.lower()] = [v]

        if not keywords:
            return

        pattern = regex.compile(
            r"(?:^|\s|[~*`_\/])(\L<words>)(?:$|\W)",
            words=list(keywords),
            flags=regex.IGNORECASE,
        )

        finds = pattern.findall(message.content)
        for keyword in finds:
            keyword = keyword.lower()
            users_to_notify = keywords.get(keyword)
            for user_id in users_to_notify:
                if user_id == message.author.id:
                    return
                member = message.guild.get_member(user_id)
                if member is None or member not in message.channel.members:
                    continue

                asyncio.ensure_future(self.send_notification(member, message, keyword))

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
        if guild_id == 0:
            try:
                self.global_notifications_cache[keyword].append(ctx.author.id)
            except KeyError:
                self.global_notifications_cache[keyword] = [ctx.author.id]
        else:
            if self.notifications_cache.get(str(guild_id)) is None:
                self.notifications_cache[str(guild_id)] = {}
            try:
                self.notifications_cache[str(guild_id)][keyword].append(ctx.author.id)
            except KeyError:
                self.notifications_cache[str(guild_id)][keyword] = [ctx.author.id]

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
        await self.create_cache()

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
            if guild_id == 0:
                guildname = "globally"
            else:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    continue

                guildname = f"in {guild}"

            rows.append(f'`"{keyword}"` *{guildname}* - triggered **{times_triggered}** times')

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
            await self.send_notification(ctx.author, ctx.message, "test", test=True)
            await ctx.send(":ok_hand:")
        except discord.errors.Forbidden:
            raise exceptions.Warning("I was unable to send you a DM. Please change your settings.")


def setup(bot):
    bot.add_cog(Notifications(bot))
