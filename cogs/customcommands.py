import discord
from discord.ext import commands
import data.database as db
import helpers.utilityfunctions as util
import helpers.log as log

command_logger = log.get_command_logger()


class CustomCommands(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """only for CommandNotFound."""
        if ctx.guild is None:
            return
        error = getattr(error, 'original', error)
        if isinstance(error, commands.CommandNotFound):
            keyword = ctx.message.content.split(' ', 1)[0][len(ctx.prefix):]
            data = db.query("SELECT response FROM customcommands WHERE guild_id = ? and command = ?",
                            (ctx.guild.id, keyword), maketuple=True)
            if data is not None:
                command_logger.info(log.custom_command_format(ctx, keyword))
                return await ctx.send(data.response)

    def bot_command_list(self, match=""):
        """Returns list of bot commands."""
        command_list = set()
        for command in self.bot.commands:
            if match in command.name:
                command_list.add(command.name)
            for alias in command.aliases:
                if match in alias:
                    command_list.add(alias)
        return command_list

    @commands.group()
    @commands.guild_only()
    async def command(self, ctx):
        """Server specific custom commmands."""
        await util.command_group_help(ctx)

    @command.command()
    async def add(self, ctx, name, *, response):
        """Add a new command."""
        if name in self.bot_command_list():
            return await ctx.send(f"Sorry, `{ctx.prefix}{name}` is already a built in command!")
        elif name in custom_command_list(ctx.guild.id):
            return await ctx.send(f"Sorry, the custom command `{ctx.prefix}{name}` "
                                  f"already exists on this server!")

        db.execute("REPLACE INTO customcommands VALUES (?, ?, ?)", (ctx.guild.id, name, response))
        await ctx.send(f"Custom command `{ctx.prefix}{name}` "
                       f"successfully added with the response `{response}`")

    @command.command()
    @commands.has_permissions()
    async def remove(self, ctx, name):
        """Remove a custom command."""
        if name not in custom_command_list(ctx.guild.id):
            return await ctx.send(f"Cannot delete command `{ctx.prefix}{name}` as it does not exist")

        db.execute("DELETE FROM customcommands WHERE guild_id = ? and command = ?", (ctx.guild.id, name))
        await ctx.send(f"Custom command `{ctx.prefix}{name}` successfully deleted")

    @command.command()
    async def search(self, ctx, name):
        """Search for a command"""
        content = discord.Embed()

        internal_rows = []
        for command in self.bot_command_list(match=name):
            internal_rows.append(f"{ctx.prefix}{command}")
        if internal_rows:
            content.add_field(name="Internal commands", value="\n".join(internal_rows))

        custom_rows = []
        for command in custom_command_list(ctx.guild.id, match=name):
            custom_rows.append(f"{ctx.prefix}{command}")
        if custom_rows:
            content.add_field(name="Custom commands", value="\n".join(custom_rows))

        if content.fields:
            await ctx.send(embed=content)
        else:
            await ctx.send("**Found nothing!**")

    @command.command()
    async def list(self, ctx):
        """List all commands on this server"""
        rows = []
        for command in custom_command_list(ctx.guild.id):
            rows.append(f"{ctx.prefix}{command}")

        if rows:
            content = discord.Embed(title=f"{ctx.guild.name} commands")
            await util.send_as_pages(ctx, content, rows, maxrows=25)
        else:
            await ctx.send("No custom commands added on this server yet")


def custom_command_list(guild_id, match=""):
    """:returns list of custom commands on server"""
    command_list = set()
    data = db.query("SELECT command FROM customcommands WHERE guild_id = ?", (guild_id,))
    if data is not None and len(data) > 0:
        for command in data:
            command = command[0]
            if match in command:
                command_list.add(command)
    return command_list


def setup(bot):
    bot.add_cog(CustomCommands(bot))
