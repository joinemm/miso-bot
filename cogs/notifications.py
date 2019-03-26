from discord.ext import commands
import data.database as db
import helpers.utilityfunctions as util


class Notifications(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.group()
    async def notification(self, ctx):
        await util.command_group_help(ctx)

    @notification.command()
    async def add(self, ctx, *, keyword):
        await ctx.message.delete()
        db.execute("REPLACE INTO notifications values(?, ?, ?)", (ctx.guild.id, ctx.author.id, keyword))
        await ctx.author.send(f"New notification for keyword `{keyword}` set in `{ctx.guild.name}` ")
        await ctx.send("Set a notification! Check your DMs <:vivismirk:532923084026544128>")

    @notification.command()
    async def remove(self, ctx, *, keyword):
        await ctx.message.delete()
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


def setup(client):
    client.add_cog(Notifications(client))
