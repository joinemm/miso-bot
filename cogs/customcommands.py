import discord
from discord.ext import commands
import data.database as db
import helpers.errormessages as errormsg
import helpers.utilityfunctions as util
import helpers.log as log

command_logger = log.get_command_logger()


class CustomCommands(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """ only for CommandNotFound"""
        error = getattr(error, 'original', error)
        if isinstance(error, commands.CommandNotFound):
            keyword = ctx.message.content.split(' ', 1)[0][len(self.client.command_prefix):]
            data = db.query("SELECT response FROM customcommands WHERE guild_id = ? and command = ?",
                            (ctx.guild.id, keyword), maketuple=True)
            if data is not None:
                command_logger.info(log.custom_command_format(ctx, keyword))
                return await ctx.send(data.response)

    def client_command_list(self, match=""):
        """:returns list of client commands"""
        command_list = set()
        for command in self.client.commands:
            if match in command.name:
                command_list.add(command.name)
            for alias in command.aliases:
                if match in alias:
                    command_list.add(alias)
        return command_list

    @commands.group()
    async def command(self, ctx):
        """Configuration for server specific custom commmands"""
        await util.command_group_help(ctx)

    @command.command()
    async def add(self, ctx, name, *, response):
        """<keyword> <response...>"""
        if name in self.client_command_list():
            return await ctx.send(f"Sorry, `{self.client.command_prefix}{name}` is already a built in command!")
        elif name in custom_command_list(ctx.guild.id):
            return await ctx.send(f"Sorry, the custom command `{self.client.command_prefix}{name}` "
                                  f"already exists on this server!")
        if len(response) < 1:
            return await ctx.send(errormsg.missing_parameter('response'))

        db.execute("REPLACE INTO customcommands VALUES (?, ?, ?)", (ctx.guild.id, name, response))
        await ctx.send(f"Custom command `{self.client.command_prefix}{name}` "
                       f"successfully added with the response `{response}`")

    @command.command()
    async def remove(self, ctx, name):
        if name not in custom_command_list(ctx.guild.id):
            return await ctx.send(f"Cannot delete command `{self.client.command_prefix}{name}` as it does not exist")

        db.execute("DELETE FROM customcommands WHERE guild_id = ? and command = ?", (ctx.guild.id, name))
        await ctx.send(f"Custom command `{self.client.command_prefix}{name}` successfully deleted")

    @command.command()
    async def search(self, ctx, name):
        content = discord.Embed()

        internal_rows = []
        for command in self.client_command_list(match=name):
            internal_rows.append(f"{self.client.command_prefix}{command}")
        if internal_rows:
            content.add_field(name="Internal commands", value="\n".join(internal_rows))

        custom_rows = []
        for command in custom_command_list(ctx.guild.id, match=name):
            custom_rows.append(f"{self.client.command_prefix}{command}")
        if custom_rows:
            content.add_field(name="Custom commands", value="\n".join(custom_rows))

        if content.fields:
            await ctx.send(embed=content)
        else:
            await ctx.send("**Found nothing!**")

    @command.command()
    async def list(self, ctx):
        rows = []
        for command in custom_command_list(ctx.guild.id):
            rows.append(f"{self.client.command_prefix}{command}")

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


def setup(client):
    client.add_cog(CustomCommands(client))
