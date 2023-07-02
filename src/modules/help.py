# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import discord
from discord.ext import commands


class EmbedHelpCommand(commands.HelpCommand):
    """HelpCommand that utilizes embeds"""

    # Set the embed colour here
    COLOUR = int("ee84ca", 16)

    def get_command_signature(self, command):
        return f"{self.context.clean_prefix}{command.qualified_name} {command.signature}"

    def get_subcommands(self, c, depth=1):
        this_cmd = ""
        if hasattr(c, "commands"):
            for subc in c.commands:
                this_cmd += "\n"
                this_cmd += f"{' '*depth}└ **{subc.name}**"
                # + (
                #     f"\n{' '*(depth+1)}{subc.short_doc}" if subc.short_doc is not None else "-"
                # )
                this_cmd += self.get_subcommands(subc, depth + 1)

        return this_cmd

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Command categories", colour=self.COLOUR)

        for (
            cog,
            bot_commands,
        ) in sorted(mapping.items(), key=lambda x: len(x[1]), reverse=True):
            if cog is None or cog.qualified_name in ["Jishaku"]:
                continue

            name = (f"{cog.icon} " if hasattr(cog, "icon") else "") + cog.qualified_name

            filtered = await self.filter_commands(bot_commands, sort=True)
            if filtered:
                embed.add_field(name=name, value=cog.description or "no description")

        embed.set_footer(
            text=f"{self.context.clean_prefix}help [category] for more details. (case sensitive)"
        )
        embed.description = "For more information on all the commands, visit https://misobot.xyz"
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(
            title=(f"{cog.icon} " if hasattr(cog, "icon") else "") + cog.qualified_name,
            colour=self.COLOUR,
        )
        if cog.description:
            embed.description = cog.description

        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered:
            embed.add_field(
                name=f"{self.get_command_signature(command)}",
                value=(command.short_doc or "no description") + self.get_subcommands(command),
                inline=False,
            )

        embed.set_footer(text=f"{self.context.clean_prefix}help [command] for more details.")
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed(title=group.qualified_name, colour=self.COLOUR)
        if group.help:
            embed.description = group.help
        elif group.short_doc:
            embed.description = group.short_doc

        if isinstance(group, commands.Group):
            filtered = await self.filter_commands(group.commands, sort=True)
            for command in filtered:
                embed.add_field(
                    name=f"{self.get_command_signature(command)}",
                    value="<:blank:749966895293268048>"
                    + (command.short_doc or "...")
                    + self.get_subcommands(command),
                    inline=False,
                )

        embed.set_footer(text=f"{self.context.clean_prefix}help [command] for more details.")
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(
            title=f"{self.get_command_signature(command)}",
            colour=self.COLOUR,
        )

        if command.aliases:
            embed.set_footer(text="Aliases: " + ", ".join(command.aliases))

        if command.help:
            embed.description = command.help
        elif command.brief:
            embed.description = command.brief
        else:
            embed.description = "..."

        await self.get_destination().send(embed=embed)

    async def group_help_brief(self, ctx: commands.Context, group):
        embed = discord.Embed(colour=self.COLOUR)
        embed.description = "`" + (ctx.prefix or ">") + group.qualified_name
        embed.description += f" [{' | '.join(c.name for c in group.commands)}]`"
        embed.set_footer(text=f"{ctx.prefix}help {group.qualified_name} for more detailed help")
        await ctx.send(embed=embed)
