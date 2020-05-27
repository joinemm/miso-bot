import discord
from discord.ext import commands
import data.database as db
import helpers.utilityfunctions as util
import re
import helpers.log as log

logger = log.get_logger(__name__)


class Notifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emojis = {}

    @commands.Cog.listener()
    async def on_ready(self):
        self.cache_emojis()

    def cache_emojis(self):
        for emoji in ["vivismirk", "hyunjinwtf"]:
            try:
                self.emojis[emoji] = self.bot.get_emoji(
                    db.query("select id from emojis where name = ?", (emoji,))[0][0]
                )
            except TypeError:
                self.emojis[emoji] = None

            if self.emojis[emoji] is None:
                logger.error(f"Unable to retrieve {emoji}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Notification handler"""
        if message.guild is None:
            return

        if message.author.id == self.bot.user.id:
            return

        keywords = db.get_keywords(message)
        if keywords is None:
            return

        for word, user_id in keywords:
            pattern = re.compile(
                r"(?:^|\W){0}(?:$|\W)".format(word), flags=re.IGNORECASE
            )
            if pattern.findall(message.content):
                member = message.guild.get_member(user_id)
                if member is None:
                    continue
                if member not in message.channel.members:
                    continue

                # create and send notification message
                await send_notification(member, message, pattern)

    @commands.group(case_insensitive=True, aliases=["noti"])
    async def notification(self, ctx):
        """Add keyword notifications on this server"""
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
            return await ctx.send(
                f"You already have this notification {self.emojis.get('hyunjinwtf')}"
            )

        db.execute(
            "REPLACE INTO notifications values(?, ?, ?)",
            (guild_id, ctx.author.id, keyword),
        )
        await ctx.author.send(
            f"New notification for keyword `{keyword}` set "
            + ("globally" if dm else f"in `{ctx.guild.name}`")
        )
        if not dm:
            await ctx.send(
                "Set a notification!"
                + ("" if dm else f" Check your DMs {self.emojis.get('vivismirk')}")
            )

    @notification.command()
    async def remove(self, ctx, *, keyword):
        """Remove notification"""
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
            return await ctx.send(
                f"You don't have that notification {self.emojis.get('hyunjinwtf')}"
            )

        db.execute(
            "DELETE FROM notifications where guild_id = ? and user_id = ? and keyword = ?",
            (guild_id, ctx.author.id, keyword),
        )
        await ctx.author.send(
            f"Notification for keyword `{keyword}` removed "
            + ("globally" if dm else f"for `{ctx.guild.name}`")
        )
        if not dm:
            await ctx.send(
                "removed a notification!"
                + ("" if dm else f" Check your DMs {self.emojis.get('vivismirk')}")
            )

    @notification.command()
    async def list(self, ctx):
        """List your current notifications"""
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
            await ctx.send(f"List sent to your DMs {self.emojis.get('vivismirk')}")


def setup(bot):
    bot.add_cog(Notifications(bot))


async def send_notification(user, message, pattern=None):
    content = discord.Embed(color=message.author.color)
    content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
    highlighted_text = re.sub(pattern, lambda x: f"**{x.group(0)}**", message.content)
    quoted_text = "> " + highlighted_text.replace("\n", "\n> ")

    content.description = f"{quoted_text}\n[Go to message]({message.jump_url})"
    content.set_footer(
        text=f"{message.guild.name} | #{message.channel.name}",
        icon_url=message.guild.icon_url,
    )
    content.timestamp = message.created_at

    await user.send(embed=content)
