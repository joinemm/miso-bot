import discord
from discord.ext import commands


class EmbedHelpCommand(commands.HelpCommand):
    """HelpCommand that utilizes embeds.
    It's pretty basic but it lacks some nuances that people might expect.
    1. It breaks if you have more than 25 cogs or more than 25 subcommands.
    2. It doesn't DM users. To do this, you have to override `get_destination`. It's simple.
    """

    # Set the embed colour here
    COLOUR = int("ee84ca", 16)

    def get_ending_note(self):
        return f"Use {self.clean_prefix}{self.invoked_with} [command | category] for more info"

    def get_command_signature(self, command):
        return f"{self.clean_prefix}{command.qualified_name} {command.signature}"

    def add_aliases_if_needed(self, embed, mapping):
        if mapping.aliases:
            embed.set_footer(text="Aliases: " + ", ".join(mapping.aliases))

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="All Commands", colour=self.COLOUR)
        description = self.context.bot.description
        if description:
            embed.description = description

        for cog, bot_commands in sorted(mapping.items(), key=lambda x: len(x[1]), reverse=True):
            if cog is None:
                name = "Other"
                # skip commands without cog, eg. the help command
                # continue
            else:
                name = cog.qualified_name
            filtered = await self.filter_commands(bot_commands, sort=True)
            if filtered:
                value = "\n".join(f"`{self.clean_prefix}{c.name}`" for c in bot_commands)
                if cog and cog.description:
                    value = f"{cog.description}\n{value}"

                embed.add_field(name=name, value=value)

        embed.set_footer(text=self.get_ending_note())
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(title=f"{cog.qualified_name} Commands", colour=self.COLOUR)
        if cog.description:
            embed.description = cog.description

        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered:
            embed.add_field(
                name=f"`{self.get_command_signature(command)}`",
                value="└ " + (command.short_doc or "..."),
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed(title=group.qualified_name, colour=self.COLOUR)
        if group.help:
            embed.description = group.help
        elif group.short_doc:
            embed.description = group.short_doc

        if isinstance(group, commands.Group):
            filtered = await self.filter_commands(group.commands, sort=False)
            for command in filtered:
                embed.add_field(
                    name=f"`{self.get_command_signature(command)}`",
                    value="└ " + (command.short_doc or "..."),
                    inline=False,
                )

        embed.set_footer(text=self.get_ending_note())
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(
            title=f"`{self.get_command_signature(command)}`",
            colour=self.COLOUR,
        )
        self.add_aliases_if_needed(embed, command)
        embed.description = ""
        if command.brief:
            embed.description += command.brief
        if command.help:
            embed.description += f" ```{command.help.format(prefix=self.clean_prefix)}```"

        await self.get_destination().send(embed=embed)

    async def group_help_brief(self, ctx, group):
        embed = discord.Embed(colour=self.COLOUR)
        embed.description = "`" + ctx.prefix + group.qualified_name
        embed.description += f" [{' | '.join(c.name for c in group.commands)}]`"
        embed.set_footer(text=f"Use {ctx.prefix}help {group.qualified_name} [subcommand] for more info")
        await ctx.send(embed=embed)
