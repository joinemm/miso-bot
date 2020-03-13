import discord
import sqlite3
import arrow
import time
import traceback
import io
from discord.ext import commands
from helpers import log, utilityfunctions as util
from data import database as db
from contextlib import redirect_stdout

logger = log.get_logger(__name__)


class Owner(commands.Cog, command_attrs=dict(hidden=True)):
    """Owner only commands."""

    def __init__(self, bot):
        self.bot = bot
    
    async def cog_check(self, ctx):
        """Check if command author is Owner."""
        return await self.bot.is_owner(ctx.author)

    def clean_codeblock(self, text):
        """Remove codeblocks and empty lines, return lines."""
        text = text.strip(' `')
        lines = text.split('\n')
        clean_lines = []

        if lines[0] in ['py', 'python']:
            lines = lines[1:]

        for line in lines:
            if line.strip() != '':
                clean_lines.append(line)

        return clean_lines

    @commands.command(rest_is_raw=True)
    async def say(self, ctx, channel, *, message):
        """Make the bot say something in a given channel."""
        if ':' in channel:
            guild, channel = channel.split(':')
            guild = await util.get_guild(ctx, guild)
            channel = await util.get_textchannel(ctx, channel, guildfilter=guild)
        else:
            channel = await self.bot.get_channel(int(channel))
            guild = channel.guild
        
        await ctx.send(f"Sending message to **{guild}** <#{channel.id}>\n> {message}")
        await channel.send(message)

    @commands.command()
    async def guilds(self, ctx):
        """Show all connected guilds."""
        membercount = len(set(self.bot.get_all_members()))
        content = discord.Embed(title=f"Total **{len(self.bot.guilds)}** guilds, **{membercount}** unique users")

        rows = []
        for guild in sorted(self.bot.guilds, key=lambda x: x.member_count, reverse=True):
            rows.append(f"[`{guild.id}`] **{guild.member_count}** members : **{guild.name}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def logout(self, ctx):
        """Shut down the bot."""
        print('logout')
        await ctx.send("Shutting down... :wave:")
        await self.bot.logout()

    @commands.group()
    async def patron(self, ctx):
        """Manage patronage."""
        await util.command_group_help(ctx)

    @patron.command(name='add')
    async def patron_add(self, ctx, user, tier, patron_since=None):
        """Add a new patron."""
        discord_user = await util.get_user(ctx, user)
        if discord_user is None:
            return await ctx.send(f"Cannot find user {user}")

        since_ts = arrow.get(patron_since).timestamp

        db.execute("INSERT INTO patrons VALUES(?, ?, ?, ?)", (discord_user.id, int(tier), since_ts, 1))
        await ctx.send(f"**{discord_user}** is now a patreon!")

    @patron.command(name='remove')
    async def patron_remove(self, ctx, user):
        """Remove a patron."""
        discord_user = await util.get_user(ctx, user)
        db.execute("DELETE FROM patrons WHERE user_id = ?",
                   (discord_user.id if discord_user is not None else int(user),))
        await ctx.send(f"Removed **{discord_user if discord_user is not None else int(user)}** from patrons")

    @patron.command(name='toggle')
    async def patron_toggle(self, ctx, user):
        """Toggle user's patron status."""
        discord_user = await util.get_user(ctx, user)
        if discord_user is None:
            return await ctx.send(f"Cannot find user {user}")

        current = util.int_to_bool(db.query("SELECT currently_active FROM patrons WHERE user_id = ?",
                                            (discord_user.id,))[0][0])
        db.execute("UPDATE patrons SET currently_active = ? WHERE user_id = ?",
                   (util.bool_to_int(not current), discord_user.id))
        await ctx.send(f"**{discord_user}** patreon activity set to **{not current}**")

    @commands.command(name='eval')
    async def evaluate(self, ctx, *, python_code):
        """Run python code."""
        env = {
            'self': self,
            'ctx': ctx
        }

        stdout = io.StringIO()

        python_lines = self.clean_codeblock(python_code)
        if not python_lines:
            return await util.send_command_help(ctx)
        
        func = "async def __ex():\n"
        for line in python_lines:
            func += f"    {line}\n"

        try:
            exec(func, env)
        except Exception as error:
            return await ctx.send(
                f":warning: Compile error\n```py\n{''.join(traceback.format_exception(None, error, None))}```"
            )

        try:
            with redirect_stdout(stdout):
                await env['__ex']()
        except Exception as error:
            result = stdout.getvalue()
            await ctx.send(
                f'```py\n{result}\n' + ''.join(traceback.format_exception(None, error, None)) + '```'
            )
        else:
            result = stdout.getvalue()
            await ctx.send(f"```py\n{result}```")

    @commands.command(name='reload')
    async def reload_module(self, ctx, *, module):
        """Reload a module."""
        try:
            self.bot.reload_extension(module)
        except Exception as error:
            await ctx.send('```py\n' + ''.join(traceback.format_exception(None, error, None)) + '\n```')
        else:
            logger.info(f"Reloaded {module}")
            await ctx.send('\N{OK HAND SIGN}')

    @commands.group()
    async def sql(self, ctx):
        """Execute SQL commands against the database."""
        await util.command_group_help(ctx)

    @sql.command(name='query')
    async def sql_query(self, ctx,  *, statement):
        """Query the database."""
        connection = sqlite3.connect(db.SQLDATABASE)
        cursor = connection.cursor()
        cursor.execute(statement)
        pretty_table = db.pp(cursor)
        connection.close()
        await ctx.send(f"```{pretty_table}```")

    @sql.command(name='execute')
    async def sql_execute(self, ctx, *, statement):
        """Execute something in the database."""
        start = time.time()
        connection = sqlite3.connect(db.SQLDATABASE)
        cursor = connection.cursor()
        cursor.execute(statement)
        connection.commit()
        connection.close()
        await ctx.send(f"```OK. Took {time.time() - start}s```")


def setup(bot):
    bot.add_cog(Owner(bot))
