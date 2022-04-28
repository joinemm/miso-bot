import asyncio

import arrow
import nextcord
from nextcord.ext import commands

from modules import exceptions, log, queries, util

command_logger = log.get_command_logger()


class CustomCommands(commands.Cog, name="Commands"):
    """Custom server commands"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "📌"

    def bot_command_list(self, match=""):
        """Returns list of bot commands"""
        command_list = []

        def add_subcommands(command):
            if hasattr(command, "commands"):
                # is a group
                for subcommand in command.commands:
                    add_subcommands(subcommand)
            else:
                # is a command
                command_list.append(command)

        for command in self.bot.commands:
            add_subcommands(command)

        if match == "":
            filtered_commands = set(command_list)
        else:
            filtered_commands = set()
            for command in command_list:
                if match.lower() in command.qualified_name.lower():
                    filtered_commands.add(command.qualified_name)
                else:
                    for alias in command.aliases:
                        if match.lower() in alias.lower():
                            filtered_commands.add(command.qualified_name)

        return filtered_commands

    async def custom_command_list(self, guild_id, match=""):
        """Returns a list of custom commands on server"""
        command_list = set()
        data = await self.bot.db.execute(
            "SELECT command_trigger FROM custom_command WHERE guild_id = %s", guild_id
        )
        for command_name in data:
            command_name = command_name[0]
            if match == "" or match in command_name:
                command_list.add(command_name)

        return command_list

    async def can_add_commands(self, ctx: commands.Context):
        """Checks if guild is restricting command adding and whether the current user can add commands"""
        if not ctx.author.guild_permissions.manage_guild and await self.bot.db.execute(
            "SELECT restrict_custom_commands FROM guild_settings WHERE guild_id = %s",
            ctx.guild.id,
            one_value=True,
        ):
            return False

        return True

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        """Check for custom commands on CommandNotFound"""
        # no custom commands in DMs
        if ctx.guild is None:
            return

        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            keyword = ctx.message.content[len(ctx.prefix) :].split(" ", 1)[0]
            response = await self.bot.db.execute(
                "SELECT content FROM custom_command WHERE guild_id = %s AND command_trigger = %s",
                ctx.guild.id,
                keyword,
                one_value=True,
            )
            if response:
                command_logger.info(log.custom_command_format(ctx, keyword))
                await ctx.send(response)
                await self.bot.db.execute(
                    """
                    INSERT INTO command_usage (guild_id, user_id, command_name, command_type)
                        VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        uses = uses + 1
                    """,
                    ctx.guild.id,
                    ctx.author.id,
                    keyword,
                    "custom",
                )

    @commands.group(aliases=["cmd"])
    @commands.guild_only()
    async def command(self, ctx: commands.Context):
        """Manage server specific custom commmands"""
        await util.command_group_help(ctx)

    @command.command()
    async def add(self, ctx: commands.Context, name, *, response):
        """Add a new custom command"""
        if not await self.can_add_commands(ctx):
            raise commands.MissingPermissions(["manage_server"])

        if name in self.bot_command_list():
            raise exceptions.Warning(f"`{ctx.prefix}{name}` is already a built in command!")
        if await self.bot.db.execute(
            "SELECT content FROM custom_command WHERE guild_id = %s AND command_trigger = %s",
            ctx.guild.id,
            name,
            one_value=True,
        ):
            raise exceptions.Warning(
                f"Custom command `{ctx.prefix}{name}` already exists on this server!"
            )

        await self.bot.db.execute(
            "INSERT INTO custom_command VALUES(%s, %s, %s, %s, %s)",
            ctx.guild.id,
            name,
            response,
            arrow.utcnow().datetime,
            ctx.author.id,
        )
        await util.send_success(
            ctx,
            f"Custom command `{ctx.prefix}{name}` added with the response \n```{response}```",
        )

    @command.command(name="remove")
    async def command_remove(self, ctx: commands.Context, name):
        """Remove a custom command"""
        owner_id = await self.bot.db.execute(
            "SELECT added_by FROM custom_command WHERE command_trigger = %s AND guild_id = %s",
            name,
            ctx.guild.id,
            one_value=True,
        )
        if not owner_id:
            raise exceptions.Warning(f"Custom command `{ctx.prefix}{name}` does not exist")

        owner = ctx.guild.get_member(owner_id)
        if (
            owner is not None
            and owner != ctx.author
            and not ctx.author.guild_permissions.manage_guild
        ):
            raise exceptions.Warning(
                f"`{ctx.prefix}{name}` can only be removed by **{owner}** unless you have `manage_server` permission."
            )

        await self.bot.db.execute(
            "DELETE FROM custom_command WHERE guild_id = %s AND command_trigger = %s",
            ctx.guild.id,
            name,
        )
        await util.send_success(ctx, f"Custom command `{ctx.prefix}{name}` has been deleted")

    @command.command(name="search")
    async def command_search(self, ctx: commands.Context, name):
        """Search for a command"""
        content = nextcord.Embed()

        internal_rows = []
        for command in self.bot_command_list(match=name):
            internal_rows.append(f"{ctx.prefix}{command}")
        if internal_rows:
            content.add_field(name="Internal commands", value="\n".join(internal_rows))

        custom_rows = []
        for command in await self.custom_command_list(ctx.guild.id, match=name):
            custom_rows.append(f"{ctx.prefix}{command}")
        if custom_rows:
            content.add_field(name="Custom commands", value="\n".join(custom_rows))

        if content.fields:
            await ctx.send(embed=content)
        else:
            await ctx.send("**Found nothing!**")

    @command.command(name="list")
    async def command_list(self, ctx: commands.Context):
        """List all commands on this server"""
        rows = []
        for command in await self.custom_command_list(ctx.guild.id):
            rows.append(f"{ctx.prefix}{command}")

        if rows:
            content = nextcord.Embed(title=f"{ctx.guild.name} custom commands")
            await util.send_as_pages(ctx, content, rows)
        else:
            raise exceptions.Info("No custom commands have been added on this server yet")

    @command.command(name="restrict")
    @commands.has_permissions(manage_guild=True)
    async def command_restrict(self, ctx: commands.Context, value: bool):
        """Restrict command management to only people with manage_server permission"""
        await queries.update_setting(ctx, "guild_settings", "restrict_custom_commands", value)
        if value:
            await util.send_success(
                ctx, "Adding custom commands is now restricted to server managers."
            )
        else:
            await util.send_success(
                ctx,
                "Adding custom commands is no longer restricted to server managers.",
            )

    @command.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def command_clear(self, ctx: commands.Context):
        """Delete all custom commands on this server"""
        count = (
            await self.bot.db.execute(
                "SELECT COUNT(*) FROM custom_command WHERE guild_id = %s",
                ctx.guild.id,
                one_value=True,
            )
            or 0
        )
        if count < 1:
            raise exceptions.Warning("This server has no custom commands yet!")

        content = nextcord.Embed(title=":warning: Are you sure?", color=int("ffcc4d", 16))
        content.description = f"This action will delete all **{count}** custom commands on this server and is **irreversible**."
        msg = await ctx.send(embed=content)

        async def confirm():
            await self.bot.db.execute(
                "DELETE FROM custom_command WHERE guild_id = %s",
                ctx.guild.id,
            )
            content.title = f":white_check_mark: Cleared commands in {ctx.guild}"
            content.description = ""
            content.color = int("77b255", 16)
            await msg.edit(embed=content)

        async def cancel():
            content.title = ":x: Action cancelled"
            content.description = ""
            content.color = int("dd2e44", 16)
            await msg.edit(embed=content)

        functions = {"✅": confirm, "❌": cancel}
        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)
        )


def setup(bot):
    bot.add_cog(CustomCommands(bot))
