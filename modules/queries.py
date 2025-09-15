# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from modules import exceptions

if TYPE_CHECKING:
    from modules.misobot import MisoBot


async def save_command_usage(ctx):
    await ctx.bot.db.execute(
        """
        INSERT INTO command_usage (guild_id, user_id, command_name, command_type)
            VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            uses = uses + 1
        """,
        ctx.guild.id,
        ctx.author.id,
        ctx.command.qualified_name,
        "internal",
    )


async def update_setting(ctx, table, setting, new_value):
    await ctx.bot.db.execute(
        f"""
        INSERT INTO {table} (guild_id, {setting})
            VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            {setting} = %s
        """,
        ctx.guild.id,
        new_value,
        new_value,
    )


async def is_donator(
    bot: "MisoBot",
    user: discord.User | discord.Member,
    unlock_tier: int | None = None,
):
    data = await bot.db.fetch_row(
        """
        SELECT donation_tier, currently_active FROM donator
        WHERE user_id = %s
        """,
        user.id,
    )
    if not data:
        return False

    if unlock_tier is not None:
        return data[1] and data[0] >= unlock_tier

    return True


async def is_vip(bot: MisoBot, user: discord.User | discord.Member):
    vips = await bot.db.fetch_flattened(
        """
        SELECT user_id FROM vip_user
        """
    )
    return vips and user.id in vips


async def is_blacklisted(ctx):
    """Check command invocation context for blacklist triggers"""
    data = await ctx.bot.db.fetch_row(
        """
        SELECT
        EXISTS (
            SELECT user_id FROM blacklisted_user WHERE user_id = %s
        ) AS global,
        EXISTS (
            SELECT guild_id FROM blacklisted_guild WHERE guild_id = %s
        ) AS guild,
        EXISTS (
            SELECT user_id FROM blacklisted_member WHERE user_id = %s AND guild_id = %s
        ) AS user,
        EXISTS (
            SELECT command_name FROM blacklisted_command WHERE command_name = %s AND guild_id = %s
        ) AS command,
        EXISTS (
            SELECT channel_id FROM blacklisted_channel WHERE channel_id = %s
        ) AS channel
        """,
        ctx.author.id,
        ctx.guild.id if ctx.guild is not None else None,
        ctx.author.id,
        ctx.guild.id if ctx.guild is not None else None,
        ctx.command.qualified_name,
        ctx.guild.id if ctx.guild is not None else None,
        ctx.channel.id,
    )

    if data[0]:
        raise exceptions.BlacklistedUser()
    if data[1]:
        raise exceptions.BlacklistedGuild()
    if data[2]:
        raise exceptions.BlacklistedMember()
    if data[3]:
        raise exceptions.BlacklistedCommand()
    if data[4]:
        raise exceptions.BlacklistedChannel()

    return True
