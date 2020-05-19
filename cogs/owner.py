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

    @commands.command(rest_is_raw=True)
    async def say(self, ctx, channel, *, message):
        """Make the bot say something in a given channel."""
        channel = self.bot.get_channel(int(channel))
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
        print('LOGGING OUT')
        await ctx.send("Shutting down... :electric_plug:")
        await self.bot.logout()

    @commands.group(case_insensitive=True)
    async def patron(self, ctx):
        """Manage patronage."""
        await util.command_group_help(ctx)

    @patron.command(name='add')
    async def patron_add(self, ctx, user: discord.User, tier: int):
        """Add a new patron."""
        since_ts = arrow.utcnow().timestamp
        db.execute(
            "INSERT INTO patrons VALUES(?, ?, ?, ?)",
            (user.id, tier, since_ts, 1)
        )
        await ctx.send(f"**{user}** is now a patron!")

    @patron.command(name='remove')
    async def patron_remove(self, ctx, user: discord.User):
        """Remove a patron."""
        db.execute(
            "DELETE FROM patrons WHERE user_id = ?",
            (user.id,)
        )
        await ctx.send(f"Removed **{user}** from patrons")

    @patron.command(name='toggle')
    async def patron_toggle(self, ctx, user: discord.User):
        """Toggle user's patron status."""
        current = util.int_to_bool(
            db.query(
                "SELECT currently_active FROM patrons WHERE user_id = ?",
                (user.id,)
            )[0][0]
        )
        db.execute(
            "UPDATE patrons SET currently_active = ? WHERE user_id = ?",
            (util.bool_to_int(not current), user.id)
        )
        await ctx.send(f"**{user}** patreon activity set to **{not current}**")

    @patron.command(name="tier")
    async def patron_tier(self, ctx, user: discord.User, new_tier: int):
        """Change user's patreon tier."""
        db.execute(
            "UPDATE patrons SET tier = ? WHERE user_id = ?",
            (new_tier, user.id)
        )
        await ctx.send(f"Patreon tier of **{user}** changed to **{new_tier}**")

    @commands.command(name='eval')
    async def evaluate(self, ctx, *, python_code):
        """Run python code."""
        env = {
            'self': self,
            'ctx': ctx
        }

        stdout = io.StringIO()

        python_lines = clean_codeblock(python_code)
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
            if result:
                await ctx.send(f"```py\n{result}```")
            else:
                await ctx.send("```OK```")

    @commands.command(name='reload')
    async def reload_cog(self, ctx, *, module):
        """Reload a cog."""
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
    async def sql_query(self, ctx, *, statement):
        """Query the database."""
        with sqlite3.connect(db.SQLDATABASE) as connection:
            cursor = connection.cursor()
            cursor.execute(statement)
            pretty_table = db.pp(cursor)

        await ctx.send(f"```{pretty_table}```")

    @sql.command(name='execute')
    async def sql_execute(self, ctx, *, statement):
        """Execute something in the database."""
        start = time.time()
        with sqlite3.connect(db.SQLDATABASE) as connection:
            cursor = connection.cursor()
            cursor.execute(statement)
            connection.commit()

        await ctx.send(f"```OK. Took {time.time() - start}s```")


def clean_codeblock(text):
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


def setup(bot):
    bot.add_cog(Owner(bot))
