# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import discord
from discord.ext import commands


class EmbedHelpCommand(commands.HelpCommand):
    """HelpCommand that utilizes embeds"""

    # Set the embed colour here
    COLOUR = int("ee84ca", 16)

    def get_command_signature(self, command: commands.Command):
        sig = " ".join(
            reversed([f"{p.name} {p.signature}".strip() for p in [command] + command.parents])
        )
        return self.context.clean_prefix + sig

    def get_subcommands(self, c, depth=0):
        this_cmd = ""
        if hasattr(c, "commands"):
            for subc in c.commands:
                this_cmd += f"\n{' '*depth}└ **{subc.name}**{self.get_subcommands(subc, depth + 1)}"

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
            title=f"{cog.icon} {cog.qualified_name}",
            colour=self.COLOUR,
            description=cog.description or "",
        )

        filtered_commands = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered_commands:
            embed.add_field(
                name=f"{self.get_command_signature(command)}",
                value=(command.short_doc or "") + self.get_subcommands(command),
                inline=False,
            )

        embed.set_footer(text=f"{self.context.clean_prefix}help [command] for more details.")
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group: commands.Group):
        embed = discord.Embed(
            title=f"{group.cog.icon} {self.get_command_signature(group)} [subcommand]",
            colour=self.COLOUR,
            description=group.help or group.short_doc or "",
        )

        embed.description += "\n\n:small_orange_diamond: __**subcommands**__ :small_orange_diamond:"
        filtered_commands = await self.filter_commands(group.commands, sort=True)
        for command in filtered_commands:
            embed.add_field(
                name=f"{command.name} {command.signature}",
                value=f"{command.short_doc} {self.get_subcommands(command)}",
                inline=False,
            )

        embed.set_footer(
            text=(
                f"{self.context.clean_prefix}help {group.qualified_name} "
                "[subcommand] for more details."
            )
        )
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(
            title=f"{command.cog.icon} {self.get_command_signature(command)}",
            colour=self.COLOUR,
            description=command.help or command.brief or "",
        )

        if command.aliases:
            embed.set_footer(text="Aliases: " + ", ".join(command.aliases))

        await self.get_destination().send(embed=embed)

    async def group_help_brief(self, ctx: commands.Context, group):
        embed = discord.Embed(colour=self.COLOUR)
        embed.description = "`" + (ctx.prefix or ">") + group.qualified_name
        embed.description += f" [{' | '.join(c.name for c in group.commands)}]`"
        embed.set_footer(text=f"{ctx.prefix}help {group.qualified_name} for more detailed help")
        await ctx.send(embed=embed)
