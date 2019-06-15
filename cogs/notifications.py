import discord
from discord.ext import commands
import data.database as db
import helpers.utilityfunctions as util
import re


class Notifications(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_message(self, message):
        """Notification handler"""
        if message.guild is None:
            return

        keywords = db.get_keywords(message.guild.id)
        if keywords is None:
            return

        for word, user_id in keywords:
            if user_id == message.author.id:
                continue
            pattern = re.compile(r'(?:^|\W){0}(?:$|\W)'.format(word), flags=re.IGNORECASE)
            if pattern.findall(message.content):
                user = message.guild.get_member(user_id)
                if user is None:
                    continue
                if user not in message.channel.members:
                    continue

                # create and send notification message
                await send_notification(user, message, pattern)

    @commands.group()
    async def notification(self, ctx):
        await util.command_group_help(ctx)

    @notification.command()
    async def add(self, ctx, *, keyword):
        await ctx.message.delete()

        check = db.query("SELECT * FROM notifications WHERE guild_id = ? and user_id = ? and keyword = ?",
                         (ctx.guild.id, ctx.author.id, keyword))
        if check is not None:
            return await ctx.send("You already have this notification <:hyunjinwtf:532922316212928532>")

        db.execute("REPLACE INTO notifications values(?, ?, ?)", (ctx.guild.id, ctx.author.id, keyword))
        await ctx.author.send(f"New notification for keyword `{keyword}` set in `{ctx.guild.name}` ")
        await ctx.send("Set a notification! Check your DMs <:vivismirk:532923084026544128>")

    @notification.command()
    async def remove(self, ctx, *, keyword):
        await ctx.message.delete()

        check = db.query("SELECT * FROM notifications WHERE guild_id = ? and user_id = ? and keyword = ?",
                         (ctx.guild.id, ctx.author.id, keyword))
        if check is None:
            return await ctx.send("You don't even have a notification for that <:hyunjinwtf:532922316212928532>")

        db.execute("DELETE FROM notifications where guild_id = ? and user_id = ? and keyword = ?",
                   (ctx.guild.id, ctx.author.id, keyword))
        await ctx.author.send(f"Notification for keyword `{keyword}` removed for `{ctx.guild.name}` ")
        await ctx.send("removed a notification! Check your DMs <:vivismirk:532923084026544128>")

    @notification.command()
    async def list(self, ctx):
        words = db.query("SELECT guild_id, keyword FROM notifications where user_id = ?",
                         (ctx.author.id,))
        data = {}
        for noti in words:
            if noti[0] in words:
                data[noti[0]].append(noti[1])
            else:
                data[noti[0]] = [noti[1]]
        text = ""
        for guild in data:
            server = self.client.get_guild(int(guild))
            if server is not None:
                text += f"**{server.name}:**"
                for word in data[guild]:
                    text += f"\n└`{word}`"
                text += "\n"
        if text == "":
            text = "**No notifications yet!**"

        await ctx.author.send(text)
        await ctx.send("List sent to your DMs <:vivismirk:532923084026544128>")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def notifytest(self, ctx):
        await send_notification(ctx.author, ctx.message)


def setup(client):
    client.add_cog(Notifications(client))


async def send_notification(user, message, pattern=None):
    content = discord.Embed(color=message.author.color)
    content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
    if pattern is not None:
        highlighted_text = re.sub(pattern, lambda x: f'**{x.group(0)}**', message.content)
    else:
        highlighted_text = message.content
    content.description = f"`>>>` {highlighted_text}\n\n" \
        f"[Go to message]({message.jump_url})"
    content.set_footer(text=f"{message.guild.name} | #{message.channel.name}")
    content.timestamp = message.created_at

    await user.send(embed=content)
