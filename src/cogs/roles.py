# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio

import discord
from discord.ext import commands

from cogs.errorhandler import ErrorHander
from modules import emojis, exceptions, queries, util
from modules.misobot import MisoBot


class Roles(commands.Cog):
    """Set up roles"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🎨"

    @commands.group(case_insensitive=True, aliases=["colourizer"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def colorizer(self, ctx: commands.Context):
        """Set up color roles for your server

        Users will be able to choose their own color with the >colorme command
        """
        await util.command_group_help(ctx)

    async def toggle_colorizer_state(self, ctx: commands.Context, value: bool):
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        await self.bot.db.execute(
            """
            INSERT INTO colorizer_settings (guild_id, enabled)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                enabled = VALUES(enabled)
            """,
            ctx.guild.id,
            value,
        )

    @colorizer.command()
    async def enable(self, ctx: commands.Context):
        """Enable the colorizer"""
        await self.toggle_colorizer_state(ctx, True)
        await util.send_success(
            ctx, "Colorizer is now **enabled** (remember to set the baserole too)"
        )

    @colorizer.command()
    async def disable(self, ctx: commands.Context):
        """Disable the colorizer"""
        await self.toggle_colorizer_state(ctx, False)
        await util.send_success(ctx, "Colorizer is now **disabled**")

    @colorizer.command()
    async def cleanup(self, ctx: commands.Context):
        """Delete all roles created by the colorizer"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        existing_roles = await self.bot.db.fetch(
            """
            SELECT color, role_id FROM colorizer_role WHERE guild_id = %s
            """,
            ctx.guild.id,
        )

        matching_roles = list(
            filter(
                lambda r: r.id in [x[1] for x in existing_roles or []],
                ctx.guild.roles,
            )
        )

        roles = "\n".join([role.mention for role in matching_roles])
        content = discord.Embed(
            title=":warning: Are you sure?",
            color=int("ffcc4d", 16),
            description=f"> This action will **permanently** delete the following roles:\n{roles}",
        )
        msg = await ctx.send(embed=content)

        async def confirm():
            await msg.edit(content=emojis.LOADING)
            for role in matching_roles:
                await role.delete(reason="Colorizer cleanup")

            await self.bot.db.execute(
                """
                DELETE FROM colorizer_role WHERE guild_id = %s
                """,
                ctx.guild.id,  # type: ignore
            )

            content.title = f":white_check_mark: Deleted all {len(matching_roles)} color roles"
            content.description = ""
            content.color = int("77b255", 16)
            await msg.edit(content=None, embed=content)

        async def cancel():
            content.title = ":x: Role cleanup cancelled"
            content.description = ""
            content.color = int("dd2e44", 16)
            await msg.edit(embed=content)

        asyncio.ensure_future(
            util.reaction_buttons(
                ctx,
                msg,
                {"✅": confirm, "❌": cancel},
                only_author=True,
                single_use=True,
            )
        )

    @colorizer.command()
    async def baserole(self, ctx: commands.Context, role: discord.Role):
        """Set the base role to inherit permissions and position from

        You should set this to something lower than the bot
        but high enough for the color to show up.
        """
        if ctx.guild is None or isinstance(ctx.author, discord.User):
            raise exceptions.CommandError("Unable to get current guild")

        if role > ctx.author.top_role:
            raise exceptions.CommandWarning(
                "You cannot set the colorizer baserole to a role higher than you in the hierarchy"
            )

        await self.bot.db.execute(
            """
            INSERT INTO colorizer_settings (guild_id, baserole_id)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                baserole_id = VALUES(baserole_id)
            """,
            ctx.guild.id,
            role.id,
        )
        await util.send_success(
            ctx, f"New color roles will now inherit permissions and position from {role.mention}"
        )

    @commands.guild_only()
    @commands.command(aliases=["colourme"])
    async def colorme(self, ctx: commands.Context, hex_color: str):
        """Get yourself a nice color role of any color you want"""
        if ctx.guild is None or isinstance(ctx.author, discord.User):
            raise exceptions.CommandError("Unable to get current guild")

        data = await self.bot.db.fetch_row(
            """
            SELECT baserole_id, enabled FROM colorizer_settings WHERE guild_id = %s
            """,
            ctx.guild.id,
        )
        try:
            baserole_id, enabled = data
        except ValueError:
            raise exceptions.CommandWarning(
                "The colorizer is not set up on this server. "
                "Please use `>colorizer` to configure it."
            )

        if not enabled:
            raise exceptions.CommandWarning(
                "The colorizer is not enabled on this server. "
                "Please use `>colorizer enable` to enable it."
            )

        try:
            color = discord.Color(value=int(hex_color.strip("#"), 16))
        except ValueError:
            raise exceptions.CommandWarning(f"`{hex_color}` is not a valid hex colour")

        baserole = ctx.guild.get_role(baserole_id) if baserole_id else None
        if baserole is None:
            raise exceptions.CommandWarning(
                "The base role to inherit permissions from is not set or doesn't exist "
                "please use `>colorizer baserole` to set it."
            )

        existing_roles = await self.bot.db.fetch(
            """
            SELECT color, role_id FROM colorizer_role WHERE guild_id = %s
            """,
            ctx.guild.id,
        )

        existing_roles_ids: list[int] = [x[1] for x in (existing_roles or [])]

        color_role = None
        if existing_roles is not None:
            existing_role_id: int | None = dict(existing_roles).get(str(color))
            color_role = ctx.guild.get_role(existing_role_id) if existing_role_id else None

            if old_roles := list(filter(lambda r: r.id in existing_roles_ids, ctx.author.roles)):
                await ctx.author.remove_roles(*old_roles, atomic=True, reason="Changed color")

            # remove manually deleted roles
            for role_id in existing_roles_ids:
                if ctx.guild.get_role(role_id) is None:
                    await self.bot.db.execute(
                        """
                        DELETE FROM colorizer_role WHERE role_id = %s
                        """,
                        role_id,
                    )

        if color_role is None:
            # create a new role
            color_role = await ctx.guild.create_role(
                name=str(color),
                permissions=baserole.permissions,
                reason=f"{ctx.author} colored themselves",
                color=color,
            )

            existing_roles_ids.append(color_role.id)

            await self.bot.db.execute(
                """
                INSERT INTO colorizer_role (guild_id, role_id, color)
                    VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    guild_id = guild_id
                """,
                ctx.guild.id,
                color_role.id,
                str(color),
            )

            before_colors = []
            acquired = []
            colors = []
            for role in ctx.guild.roles:
                if role.id in existing_roles_ids:
                    colors.append(role)
                else:
                    acquired.append(role)

                if role == baserole:
                    before_colors += acquired
                    acquired = []

            final = before_colors + colors + acquired
            payload = [{"id": role.id, "position": i} for i, role in enumerate(final)]
            await self.bot.http.move_role_position(
                ctx.guild.id,
                payload,
                reason="Colorizer action",
            )  # type: ignore

        # color the user
        await ctx.author.add_roles(color_role)

        await ctx.send(
            embed=discord.Embed(
                description=f":art: Colored you `{color}`",
                color=color,
            )
        )

        # clean up any roles that are left with 0 users
        unused_roles = filter(
            lambda r: r.id in [x[1] for x in existing_roles or []] and len(r.members) == 0,
            ctx.guild.roles,
        )
        for role in unused_roles:
            await role.delete(reason="Unused role")

    @commands.group(case_insensitive=True)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rolepicker(self, ctx: commands.Context):
        """Manage the rolepicker"""
        await util.command_group_help(ctx)

    @rolepicker.command(name="add")
    async def rolepicker_add(self, ctx: commands.Context, role: discord.Role, *, name):
        """Add a role to the rolepicker"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

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
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        role_id = await self.bot.db.fetch_value(
            """
            SELECT role_id FROM rolepicker_role WHERE guild_id = %s AND role_name = %s
            """,
            ctx.guild.id,
            name.lower(),
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
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        data = (
            await self.bot.db.fetch(
                """
            SELECT role_name, role_id FROM rolepicker_role
            WHERE guild_id = %s
            """,
                ctx.guild.id,
            )
            or []
        )
        content = discord.Embed(
            title=f":scroll: Available roles in {ctx.guild.name}",
            color=int("ffd983", 16),
        )
        if rows := [f"`{role_name}` : <@&{role_id}>" for role_name, role_id in sorted(data)]:
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
    async def on_message(self, message: discord.Message):
        """Rolechannel message handler"""
        await self.bot.wait_until_ready()

        if message.guild is None or not isinstance(message.author, discord.Member):
            return

        if message.channel.id not in self.bot.cache.rolepickers:
            return

        is_enabled = await self.bot.db.fetch_value(
            """
            SELECT is_enabled FROM rolepicker_settings WHERE guild_id = %s AND channel_id = %s
            """,
            message.guild.id,
            message.channel.id,
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
        if not isinstance(errorhandler, ErrorHander):
            return message.channel.send("Internal Error: Could not get ErrorHandler")

        if command in ["+", "-"]:
            role_id = await self.bot.db.fetch_value(
                """
                SELECT role_id FROM rolepicker_role WHERE guild_id = %s AND role_name = %s
                """,
                message.guild.id,
                rolename.lower(),
            )
            role = message.guild.get_role(role_id) if role_id else None
            if role is None:
                await message.reply(f':warning: Role `"{rolename}"` not found!')

            elif command == "+":
                try:
                    await message.author.add_roles(role)
                except discord.errors.Forbidden:
                    await message.reply(":warning: I don't have permission to give you this role!")
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
                    await message.reply(
                        ":warning: I don't have permission to remove this role from you!"
                    )
                else:
                    await message.channel.send(
                        embed=discord.Embed(
                            description=f":x: Removed your role {role.mention}",
                            color=role.color,
                        ),
                    )
        else:
            await message.reply(
                f":warning: Unknown action `{command}`. "
                "Use `+name` to add roles and `-name` to remove them."
            )

        await asyncio.sleep(5)
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass


async def setup(bot):
    await bot.add_cog(Roles(bot))
