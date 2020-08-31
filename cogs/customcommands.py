import discord
import arrow
from discord.ext import commands
import data.database as db
import helpers.utilityfunctions as util
import helpers.log as log

command_logger = log.get_command_logger()


class CustomCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def bot_command_list(self, match=""):
        """Returns list of bot commands."""
        command_list = set()
        for command in self.bot.commands:
            if match.lower() in command.name.lower():
                command_list.add(command.name)
            for alias in command.aliases:
                if match.lower() in alias.lower():
                    command_list.add(alias)

        return command_list

    async def everyone_or_manager(ctx):
        if ctx.author.guild_permissions.manage_guild:
            return True

        setting = db.get_setting(ctx.guild.id, "custom_commands_everyone")
        if setting != 0:
            return True
        else:
            raise commands.MissingPermissions(["manage_server"])

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """only for CommandNotFound."""
        if ctx.guild is None:
            return
        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            keyword = ctx.message.content[len(ctx.prefix) :].split(" ", 1)[0]
            data = db.query(
                """SELECT response FROM customcommands
                WHERE guild_id = ? and command = ?""",
                (ctx.guild.id, keyword),
            )
            if data is not None:
                command_logger.info(log.custom_command_format(ctx, keyword))
                await ctx.send(data[0][0])
                db.log_custom_command_usage(ctx, keyword)

    @commands.group()
    @commands.guild_only()
    async def command(self, ctx):
        """Server specific custom commmands."""
        await util.command_group_help(ctx)

    @command.command()
    @commands.check(everyone_or_manager)
    async def add(self, ctx, name, *, response):
        """Add a new custom command."""
        if name in self.bot_command_list():
            return await ctx.send(f"Sorry, `{ctx.prefix}{name}` is already a built in command!")
        elif name in custom_command_list(ctx.guild.id):
            return await ctx.send(
                f"Sorry, the custom command `{ctx.prefix}{name}` "
                f"already exists on this server!"
            )

        db.execute(
            """INSERT INTO customcommands VALUES (?, ?, ?, ?, ?)""",
            (ctx.guild.id, name, response, arrow.utcnow().timestamp, ctx.author.id),
        )
        await ctx.send(
            f"Custom command `{ctx.prefix}{name}` "
            f"successfully added with the response `{response}`"
        )

    @command.command()
    async def remove(self, ctx, name):
        """Remove a custom command."""
        if name not in custom_command_list(ctx.guild.id):
            return await ctx.send(
                f"Cannot delete command `{ctx.prefix}{name}` as it does not exist"
            )

        owner = db.query("""SELECT added_by FROM customcommands WHERE command = ?""", (name,))
        if owner is not None and owner != ctx.author.id:
            if not ctx.author.guild_permissions.manage_guild:
                return await ctx.send(
                    ":warning: You can only remove commands you have added, "
                    "unless you have the `manage_server` permission."
                )

        db.execute(
            """DELETE FROM customcommands
            WHERE guild_id = ? and command = ?""",
            (ctx.guild.id, name),
        )
        await ctx.send(f"Custom command `{ctx.prefix}{name}` successfully deleted")

    @command.command()
    async def search(self, ctx, name):
        """Search for a command."""
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
        """List all commands on this server."""
        rows = []
        for command in custom_command_list(ctx.guild.id):
            rows.append(f"{ctx.prefix}{command}")

        if rows:
            content = discord.Embed(title=f"{ctx.guild.name} commands")
            await util.send_as_pages(ctx, content, rows, maxrows=25)
        else:
            await ctx.send("No custom commands added on this server yet")

    @command.command(name="eligibility")
    async def command_eligibility(self, ctx, value: bool):
        """Change whether everyone can add commands, or only server managers"""
        db.update_setting(ctx.guild.id, "custom_commands_everyone", util.bool_to_int(value))
        if value:
            await ctx.send("Everyone can now add custom commands!")
        else:
            await ctx.send("Adding commands now requires the `manage_server` permission!")


def custom_command_list(guild_id, match=""):
    """Returns a list of custom commands on server."""
    command_list = set()
    data = db.query(
        """SELECT command FROM customcommands
        WHERE guild_id = ?""",
        (guild_id,),
    )
    if data is not None and len(data) > 0:
        for command in data:
            command = command[0]
            if match in command:
                command_list.add(command)

    return command_list


def setup(bot):
    bot.add_cog(CustomCommands(bot))
