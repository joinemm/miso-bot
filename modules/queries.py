from modules import exceptions, log

logger = log.get_logger(__name__)


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


async def is_donator(ctx, user, unlock_tier=1):
    if user.id == ctx.bot.owner_id:
        return True

    tier = await ctx.bot.db.execute(
        """
        SELECT donation_tier FROM donator
        WHERE user_id = %s
          AND currently_active
        """,
        user.id,
        one_value=True,
    )
    return tier and tier >= unlock_tier


async def is_blacklisted(ctx):
    """Check command invocation context for blacklist triggers."""
    data = await ctx.bot.db.execute(
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
        one_row=True,
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
