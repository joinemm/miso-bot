from discord.ext import commands
import discord
import helpers.log as log
import helpers.utilityfunctions as util
import data.database as db
import sqlite3
import arrow

logger = log.get_logger(__name__)


class Owner(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(hidden=True, rest_is_raw=True)
    @commands.is_owner()
    async def say(self, ctx, channel, *, message):
        """Make the bot say something in a given channel"""
        channel = await util.get_textchannel(ctx, channel)
        await channel.send(message)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def guilds(self, ctx):
        """Show all connected guilds"""
        membercount = len(set(self.client.get_all_members()))
        content = discord.Embed(title=f"Total **{len(self.client.guilds)}** guilds, **{membercount}** unique users")

        rows = []
        for guild in sorted(self.client.guilds, key=lambda x: x.member_count, reverse=True):
            rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def logout(self, ctx):
        """Shuts down the bot"""
        print('logout')
        await ctx.send("Shutting down... :wave:")
        await self.client.logout()

    @commands.group(hidden=True, case_insensitive=True)
    @commands.is_owner()
    async def patron(self, ctx):
        await util.command_group_help(ctx)

    @patron.command(name='add')
    @commands.is_owner()
    async def patron_add(self, ctx, user, tier, patron_since=None):
        discord_user = await util.get_user(ctx, user)
        if discord_user is None:
            return await ctx.send(f"Cannot find user {user}")

        since_ts = arrow.get(patron_since).timestamp

        db.execute("INSERT INTO patrons VALUES(?, ?, ?, ?)", (discord_user.id, int(tier), since_ts, 1))
        await ctx.send(f"**{discord_user}** is now a patreon!")

    @patron.command(name='remove')
    @commands.is_owner()
    async def patron_remove(self, ctx, user):
        discord_user = await util.get_user(ctx, user)
        db.execute("DELETE FROM patrons WHERE user_id = ?",
                   (discord_user.id if discord_user is not None else int(user),))
        await ctx.send(f"Removed **{discord_user if discord_user is not None else int(user)}** from patrons")

    @patron.command(name='toggle')
    @commands.is_owner()
    async def patron_toggle(self, ctx, user):
        discord_user = await util.get_user(ctx, user)
        if discord_user is None:
            return await ctx.send(f"Cannot find user {user}")

        current = util.int_to_bool(db.query("SELECT currently_active FROM patrons WHERE user_id = ?",
                                            (discord_user.id,))[0][0])
        db.execute("UPDATE patrons SET currently_active = ? WHERE user_id = ?",
                   (util.bool_to_int(not current), discord_user.id))
        await ctx.send(f"**{discord_user}** patreon activity set to **{not current}**")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sql(self, ctx, *, statement):
        connection = sqlite3.connect(db.SQLDATABASE)
        cursor = connection.cursor()
        cursor.execute(statement)

        pretty_table = db.pp(cursor)
        await ctx.send(f"```{pretty_table}```")

        connection.close()


def setup(client):
    client.add_cog(Owner(client))
