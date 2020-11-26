from helpers import log, exceptions

logger = log.get_logger(__name__)


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
        ctx.guild.id,
        ctx.author.id,
        ctx.guild.id,
        ctx.command.name,
        ctx.guild.id,
        ctx.channel.id,
        one_row=True,
    )

    if data[0]:
        raise exceptions.BlacklistedUser()
    elif data[1]:
        raise exceptions.BlacklistedGuild()
    elif data[2]:
        raise exceptions.BlacklistedMember()
    elif data[3]:
        raise exceptions.BlacklistedCommand()
    elif data[4]:
        raise exceptions.BlacklistedChannel()
    else:
        return True
