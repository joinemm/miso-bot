import discord
from discord.ext import commands


class EmbedHelpCommand(commands.HelpCommand):
    """
    HelpCommand that utilizes embeds.
    It's pretty basic but it lacks some nuances that people might expect.
    1. It breaks if you have more than 25 cogs or more than 25 subcommands.
    2. It doesn't DM users. To do this, you have to override `get_destination`. It's simple.
    """

    # Set the embed colour here
    COLOUR = int("ee84ca", 16)

    def get_command_signature(self, command):
        return f"{self.clean_prefix}{command.qualified_name} {command.signature}"

    def get_subcommands(self, c, depth=1):
        this_cmd = ""
        if hasattr(c, "commands"):
            for subc in c.commands:
                this_cmd += f"\n{' '*depth}└ **{subc.name}**" + (
                    f"\n{' '*(depth+1)}{subc.short_doc}" if subc.short_doc is not None else "-"
                )
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
                embed.add_field(name=name, value=cog.description or "...")

        embed.set_footer(
            text=f"{self.clean_prefix}help [category] for more details. (case sensitive)"
        )
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
                value=(f"{command.short_doc}\n" if command.short_doc is not None else "-")
                + self.get_subcommands(command),
                inline=False,
            )

        embed.set_footer(text=f"{self.clean_prefix}help [command] for more details.")
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

        embed.set_footer(text=f"{self.clean_prefix}help [command] for more details.")
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

    async def group_help_brief(self, ctx, group):
        embed = discord.Embed(colour=self.COLOUR)
        embed.description = "`" + ctx.prefix + group.qualified_name
        embed.description += f" [{' | '.join(c.name for c in group.commands)}]`"
        embed.set_footer(text=f"{ctx.prefix}help {group.qualified_name} for more detailed help")
        await ctx.send(embed=embed)
