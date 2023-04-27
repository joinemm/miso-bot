# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import json

import arrow
import discord
from discord.ext import commands
from loguru import logger

from modules import emojis, exceptions, queries, util
from modules.misobot import MisoBot


class CustomCommands(commands.Cog, name="Commands"):
    """Custom server commands"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
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
        data = await self.bot.db.fetch_flattened(
            "SELECT command_trigger FROM custom_command WHERE guild_id = %s", guild_id
        )
        return {
            command_trigger for command_trigger in data if match == "" or match in command_trigger
        }

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        """Check for custom commands on CommandNotFound"""
        # no custom commands in DMs
        if ctx.guild is None:
            return

        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            keyword = ctx.message.content[len(ctx.prefix or "") :].split(" ", 1)[0]
            response = await self.bot.db.fetch_value(
                "SELECT content FROM custom_command WHERE guild_id = %s AND command_trigger = %s",
                ctx.guild.id,
                keyword,
            )
            if response:
                logger.info(util.log_command_format(ctx, extra="(CUSTOM)"))
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

    @commands.group(aliases=["cmd", "commands", "tag"])
    @commands.guild_only()
    async def command(self, ctx: commands.Context):
        """Manage server specific custom commmands"""
        await util.command_group_help(ctx)

    @command.command()
    async def add(self, ctx: commands.Context, name, *, response):
        """Add a new custom command"""
        if not isinstance(ctx.author, discord.Member):
            raise exceptions.CommandError("Unable to get author member.")

        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if not ctx.author.guild_permissions.manage_guild and await self.bot.db.fetch_value(
            "SELECT restrict_custom_commands FROM guild_settings WHERE guild_id = %s",
            ctx.guild.id,
        ):
            raise commands.MissingPermissions(["manage_server"])

        if name in self.bot_command_list():
            raise exceptions.CommandWarning(f"`{ctx.prefix}{name}` is already a built in command!")
        if await self.bot.db.fetch_value(
            "SELECT content FROM custom_command WHERE guild_id = %s AND command_trigger = %s",
            ctx.guild.id,
            name,
        ):
            raise exceptions.CommandWarning(
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

        if not isinstance(ctx.author, discord.Member):
            raise exceptions.CommandError("Unable to get author member.")

        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        owner_id = await self.bot.db.fetch_value(
            "SELECT added_by FROM custom_command WHERE command_trigger = %s AND guild_id = %s",
            name,
            ctx.guild.id,
        )
        if not owner_id:
            raise exceptions.CommandWarning(f"Custom command `{ctx.prefix}{name}` does not exist")

        owner = ctx.guild.get_member(owner_id)
        if (
            owner is not None
            and owner != ctx.author
            and not ctx.author.guild_permissions.manage_guild
        ):
            raise exceptions.CommandWarning(
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
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        content = discord.Embed()

        if internal_rows := [
            f"{ctx.prefix}{command}" for command in self.bot_command_list(match=name)
        ]:
            content.add_field(name="Internal commands", value="\n".join(internal_rows))

        custom_rows = [
            f"{ctx.prefix}{command}"
            for command in await self.custom_command_list(ctx.guild.id, match=name)
        ]
        if custom_rows:
            content.add_field(name="Custom commands", value="\n".join(custom_rows))

        if content.fields:
            await ctx.send(embed=content)
        else:
            await ctx.send("**Found nothing!**")

    @command.command(name="list")
    async def command_list(self, ctx: commands.Context):
        """List all commands on this server"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        rows = [
            f"{ctx.prefix}{command}" for command in await self.custom_command_list(ctx.guild.id)
        ]
        if rows:
            content = discord.Embed(title=f"{ctx.guild.name} custom commands")
            await util.send_as_pages(ctx, content, rows)
        else:
            raise exceptions.CommandInfo("No custom commands have been added on this server yet")

    @commands.is_owner()
    @command.command(name="import")
    async def command_import(self, ctx: commands.Context):
        """Attach a json file in format {command: xxx, text: xxx}"""
        jsonfile = ctx.message.attachments[0]
        imported = json.loads(await jsonfile.read())
        tasks = []
        for command in imported:
            name = command["command"]
            text = command["text"]
            tasks.append(self.import_command(ctx, name, text))

        load = await ctx.send(emojis.LOADING)
        results = await asyncio.gather(*tasks)
        await load.delete()
        await util.send_tasks_result_list(
            ctx,
            successful_operations=[r[1] for r in filter(lambda x: x[0], results)],
            failed_operations=[r[1] for r in filter(lambda x: not x[0], results)],
        )

    async def import_command(self, ctx: commands.Context, name, text):
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if name in self.bot_command_list():
            return False, f"`{ctx.prefix}{name}` is already a built in command!"
        if await self.bot.db.fetch_value(
            "SELECT content FROM custom_command WHERE guild_id = %s AND command_trigger = %s",
            ctx.guild.id,
            name,
        ):
            return False, f"Custom command `{ctx.prefix}{name}` already exists on this server!"

        await self.bot.db.execute(
            "INSERT INTO custom_command VALUES(%s, %s, %s, %s, %s)",
            ctx.guild.id,
            name,
            text,
            arrow.utcnow().datetime,
            ctx.author.id,
        )
        return True, name

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

        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")
        guild = ctx.guild

        count = (
            await self.bot.db.fetch_value(
                "SELECT COUNT(*) FROM custom_command WHERE guild_id = %s",
                guild.id,
            )
            or 0
        )
        if count < 1:
            raise exceptions.CommandWarning("This server has no custom commands yet!")

        content = discord.Embed(title=":warning: Are you sure?", color=int("ffcc4d", 16))
        content.description = f"This action will delete all **{count}** custom commands on this server and is **irreversible**."
        msg = await ctx.send(embed=content)

        async def confirm():
            await self.bot.db.execute(
                "DELETE FROM custom_command WHERE guild_id = %s",
                guild.id,
            )
            content.title = f":white_check_mark: Cleared commands in {guild}"
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


async def setup(bot):
    await bot.add_cog(CustomCommands(bot))
