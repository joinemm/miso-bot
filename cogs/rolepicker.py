import asyncio

import discord
from discord.ext import commands

from modules import exceptions, queries, util


class Rolepicker(commands.Cog):
    """Set up a role picker"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🧮"

    @commands.group(case_insensitive=True)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rolepicker(self, ctx: commands.Context):
        """Manage the rolepicker"""
        await util.command_group_help(ctx)

    @rolepicker.command(name="add")
    async def rolepicker_add(self, ctx: commands.Context, role: discord.Role, *, name):
        """Add a role to the rolepicker"""
        await self.bot.db.execute(
            """
            INSERT INTO rolepicker_role (guild_id, role_name, role_id)
                VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                role_id = VALUES(role_id)
            """,
            ctx.guild.id,
            name.lower(),
            role.id,
        )
        await util.send_success(
            ctx,
            f"{role.mention} can now be acquired by typing `+{name}` in the rolepicker channel.",
        )

    @rolepicker.command(name="remove")
    async def rolepicker_remove(self, ctx: commands.Context, *, name):
        """Remove a role from the rolepicker"""
        role_id = await self.bot.db.execute(
            """
            SELECT role_id FROM rolepicker_role WHERE guild_id = %s AND role_name = %s
            """,
            ctx.guild.id,
            name.lower(),
            one_value=True,
        )
        if not role_id:
            raise exceptions.CommandWarning(
                f"Could not find role with the name `{name}` in the picker."
            )

        await self.bot.db.execute(
            """
            DELETE FROM rolepicker_role WHERE guild_id = %s AND role_name = %s
            """,
            ctx.guild.id,
            name.lower(),
        )
        await util.send_success(
            ctx,
            f"<@&{role_id}> can no longer be acquired from the rolepicker channel.",
        )

    @rolepicker.command(name="channel")
    async def rolepicker_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel you want to add and remove roles in"""
        await queries.update_setting(ctx, "rolepicker_settings", "channel_id", channel.id)
        self.bot.cache.rolepickers.add(channel.id)
        await util.send_success(
            ctx,
            f"Rolepicker channel set to {channel.mention}\n"
            f"Use `{ctx.prefix}rolepicker enabled true` once you've set everything up.",
        )

    @rolepicker.command(name="list")
    async def rolepicker_list(self, ctx: commands.Context):
        """List all the roles currently available for picking"""
        data = await self.bot.db.execute(
            """
            SELECT role_name, role_id FROM rolepicker_role
            WHERE guild_id = %s
            """,
            ctx.guild.id,
        )
        content = discord.Embed(
            title=f":scroll: Available roles in {ctx.guild.name}",
            color=int("ffd983", 16),
        )
        rows = []
        for role_name, role_id in sorted(data):
            rows.append(f"`{role_name}` : <@&{role_id}>")

        if rows:
            await util.send_as_pages(ctx, content, rows)
        else:
            content.description = "Nothing yet!"
            await ctx.send(embed=content)

    @rolepicker.command(name="enabled")
    async def rolepicker_enabled(self, ctx: commands.Context, value: bool):
        """Enable or disable the rolepicker"""
        await queries.update_setting(ctx, "rolepicker_settings", "is_enabled", value)
        await util.send_success(ctx, f"Rolepicker is now **{'enabled' if value else 'disabled'}**")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Rolechannel message handler"""
        if not self.bot.is_ready():
            return

        if message.guild is None:
            return

        if message.channel.id not in self.bot.cache.rolepickers:
            return

        is_enabled = await self.bot.db.execute(
            """
            SELECT is_enabled FROM rolepicker_settings WHERE guild_id = %s AND channel_id = %s
            """,
            message.guild.id,
            message.channel.id,
            one_value=True,
        )
        if not is_enabled:
            return

        # delete all bot messages in rolepicker channel
        if message.author.bot:
            await asyncio.sleep(5)
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass
            return

        command = message.content[0]
        rolename = message.content[1:].strip()
        errorhandler = self.bot.get_cog("ErrorHander")
        if command in ["+", "-"]:
            role_id = await self.bot.db.execute(
                """
                SELECT role_id FROM rolepicker_role WHERE guild_id = %s AND role_name = %s
                """,
                message.guild.id,
                rolename.lower(),
                one_value=True,
            )
            role = message.guild.get_role(role_id)
            if role is None:
                await errorhandler.send(
                    message.channel, "warning", f'Role `"{rolename}"` not found!'
                )

            elif command == "+":
                try:
                    await message.author.add_roles(role)
                except discord.errors.Forbidden:
                    await errorhandler.send(
                        message.channel,
                        "error",
                        "I don't have permission to give you this role!",
                    )
                else:
                    await message.channel.send(
                        embed=discord.Embed(
                            description=f":white_check_mark: Added {role.mention} to your roles",
                            color=role.color,
                        ),
                    )
            elif command == "-":
                try:
                    await message.author.remove_roles(role)
                except discord.errors.Forbidden:
                    await errorhandler.send(
                        message.channel,
                        "error",
                        "I don't have permission to remove this role from you!",
                    )
                else:
                    await message.channel.send(
                        embed=discord.Embed(
                            description=f":x: Removed your role {role.mention}",
                            color=role.color,
                        ),
                    )
        else:
            await errorhandler.send(
                message.channel,
                "warning",
                f"Unknown action `{command}`. Use `+name` to add roles and `-name` to remove them.",
            )

        await asyncio.sleep(5)
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass


async def setup(bot):
    await bot.add_cog(Rolepicker(bot))
