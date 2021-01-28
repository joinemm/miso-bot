import discord
from discord.ext import commands
from libraries import emoji_literals
from modules import queries, exceptions, util


class ChannelSetting(commands.TextChannelConverter):
    """This enables removing a channel from the database in the same command that adds it."""

    async def convert(self, ctx, argument):
        if argument.lower() in ["disable", "none", "delete", "remove"]:
            return None
        else:
            return await super().convert(ctx, argument)


class Configuration(commands.Cog):
    """Bot configuration"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "⚙️"

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx, prefix):
        """
        Set a custom command prefix for this server.

        Usage:
            >prefix <text>
            >prefix \"<text with spaces>\"
        """
        if prefix.strip() == "":
            raise exceptions.Warning("Prefix cannot be empty.")

        if prefix.startswith(" "):
            raise exceptions.Warning("Prefix cannot start with a space.")

        if len(prefix) > 32:
            raise exceptions.Warning("Prefix cannot be over 32 characters.")

        prefix = prefix.lstrip()
        await self.bot.db.execute(
            """
            INSERT INTO guild_prefix (guild_id, prefix)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                prefix = VALUES(prefix)
            """,
            ctx.guild.id,
            prefix,
        )
        self.bot.cache.prefixes[str(ctx.guild.id)] = prefix
        await util.send_success(
            ctx,
            f"Command prefix for this server is now `{prefix}`. "
            f"Example command usage: {prefix}ping",
        )

    @commands.group(name="greeter")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def greeter(self, ctx):
        """Configure the greeter/welcome message."""
        await util.command_group_help(ctx)

    @greeter.command(name="toggle", aliases=["enabled"])
    async def greeter_toggle(self, ctx, value: bool):
        """Enable or disable the greeter."""
        await queries.update_setting(ctx, "greeter_settings", "is_enabled", value)
        if value:
            await util.send_success(ctx, "Greeter is now **enabled**")
        else:
            await util.send_success(ctx, "Greeter is now **disabled**")

    @greeter.command(name="channel")
    async def greeter_channel(self, ctx, *, channel: discord.TextChannel):
        """Set the greeter channel."""
        await queries.update_setting(ctx, "greeter_settings", "channel_id", channel.id)
        await util.send_success(ctx, f"Greeter channel is now {channel.mention}")

    @greeter.command(name="message")
    async def greeter_message(self, ctx, *, message):
        """
        Change the greeter welcome message format.
        Use with "default" to reset to the default format.
        """
        if message.lower() == "default":
            message = None

        await queries.update_setting(ctx, "greeter_settings", "message_format", message)

        preview = util.create_welcome_embed(ctx.author, ctx.guild, message)
        await ctx.send(
            f":white_check_mark: New welcome message format set:\n```{message}```Preview:",
            embed=preview,
        )

    @commands.group(name="goodbyemessage", aliases=["goodbyemessages"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def goodbyemessage(self, ctx):
        """Configure the goodbye message."""
        await util.command_group_help(ctx)

    @goodbyemessage.command(name="toggle", aliases=["enabled"])
    async def goodbye_toggle(self, ctx, value: bool):
        """Enable or disable the goodbye messages."""
        await queries.update_setting(ctx, "goodbye_settings", "is_enabled", value)
        if value:
            await util.send_success(ctx, "Goodbye messages are now **enabled**")
        else:
            await util.send_success(ctx, "Goodbye messages are now **disabled**")

    @goodbyemessage.command(name="channel")
    async def goodbye_channel(self, ctx, *, channel: discord.TextChannel):
        """Set the goodbye messages channel."""
        await queries.update_setting(ctx, "goodbye_settings", "channel_id", channel.id)
        await util.send_success(ctx, f"Goodbye messages channel is now {channel.mention}")

    @goodbyemessage.command(name="message")
    async def goodbye_message(self, ctx, *, message):
        """
        Change the goodbye message format.
        Use with "default" to reset to the default format.
        """
        if message.lower() == "default":
            message = None

        await queries.update_setting(ctx, "goodbye_settings", "message_format", message)

        preview = util.create_goodbye_message(ctx.author, ctx.guild, message)
        await ctx.send(
            f":white_check_mark: New goodbye message format set:\n```{message}```Preview:\n\n{preview}"
        )

    @commands.group(name="logger")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def logger(self, ctx):
        """Configure the logging of various guild events."""
        await util.command_group_help(ctx)

    @logger.command(name="members")
    async def logger_members(self, ctx, *, channel: ChannelSetting):
        """
        Set channel for member leaves and joins logging.

        Set to \"none\" to disable.
        """
        await queries.update_setting(
            ctx,
            "logging_settings",
            "member_log_channel_id",
            channel.id if channel is not None else None,
        )
        if channel is None:
            await util.send_success(ctx, "Members logging **disabled**")
        else:
            await util.send_success(ctx, f"Member changes will now be logged to {channel.mention}")

    @logger.command(name="bans")
    async def logger_bans(self, ctx, *, channel: ChannelSetting):
        """
        Set channel where bans are announced.

        Set to \"none\" to disable.
        """
        await queries.update_setting(
            ctx,
            "logging_settings",
            "ban_log_channel_id",
            channel.id if channel is not None else None,
        )
        if channel is None:
            await util.send_success(ctx, "Bans logging **disabled**")
        else:
            await util.send_success(ctx, f"Bans will now be logged to {channel.mention}")

    @logger.group(name="deleted")
    async def logger_deleted(self, ctx):
        """Configure logging of deleted messages."""
        await util.command_group_help(ctx)

    @logger_deleted.command(name="channel")
    async def deleted_channel(self, ctx, *, channel: ChannelSetting):
        """
        Set channel where deleted messages are logged.

        Set to \"none\" to disable.
        """
        await queries.update_setting(
            ctx,
            "logging_settings",
            "message_log_channel_id",
            channel.id if channel is not None else None,
        )
        if channel is None:
            await util.send_success(ctx, "Deleted message logging **disabled**")
        else:
            await util.send_success(
                ctx, f"Deleted messages will now be logged to {channel.mention}"
            )

    @logger_deleted.command(name="ignore")
    async def deleted_ignore(self, ctx, *, channel: discord.TextChannel):
        """Ignore channels from being logged in deleted messages."""
        await self.bot.db.execute(
            "INSERT IGNORE message_log_ignore (guild_id, channel_id) VALUES (%s, %s)",
            ctx.guild.id,
            channel.id,
        )
        await util.send_success(
            ctx, f"No longer logging any messages deleted in {channel.mention}"
        )

    @logger_deleted.command(name="unignore")
    async def deleted_unignore(self, ctx, *, channel: discord.TextChannel):
        """Unignore channel from logging deleted messages."""
        await self.bot.db.execute(
            "DELETE FROM message_log_ignore WHERE guild_id = %s and channel_id = %s",
            ctx.guild.id,
            channel.id,
        )
        await util.send_success(
            ctx, f"{channel.mention} is no longer being ignored from deleted message logging."
        )

    @commands.command(aliases=["levelups"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def levelup(self, ctx, value: bool):
        """Enable or disable levelup messages."""
        await queries.update_setting(ctx, "guild_settings", "levelup_messages", value)
        self.bot.cache.levelupmessage[str(ctx.guild.id)] = value
        if value:
            await util.send_success(ctx, "Level up messages are now **enabled**")
        else:
            await util.send_success(ctx, "Level up messages are now **disabled**")

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def starboard(self, ctx):
        """Configure the starboard."""
        await util.command_group_help(ctx)

    @starboard.command(name="channel")
    async def starboard_channel(self, ctx, channel: discord.TextChannel):
        """Set starboard channel."""
        await queries.update_setting(ctx, "starboard_settings", "channel_id", channel.id)
        await util.send_success(ctx, f"Starboard channel is now {channel.mention}")

    @starboard.command(name="amount")
    async def starboard_amount(self, ctx, amount: int):
        """Change the amount of reactions required to starboard a message."""
        await queries.update_setting(ctx, "starboard_settings", "reaction_count", amount)
        emoji_name, emoji_id, emoji_type = await self.bot.db.execute(
            """
            SELECT emoji_name, emoji_id, emoji_type
            FROM starboard_settings WHERE guild_id = %s
            """,
            ctx.guild.id,
            one_row=True,
        )
        if emoji_type == "custom":
            emoji = self.bot.get_emoji(emoji_id)
        else:
            emoji = emoji_name

        await util.send_success(
            ctx, f"Messages now need **{amount}** {emoji} reactions to get into the starboard."
        )

    @starboard.command(name="toggle", aliases=["enabled"])
    async def starboard_toggle(self, ctx, value: bool):
        """Enable or disable the starboard."""
        await queries.update_setting(ctx, "starboard_settings", "is_enabled", value)
        if value:
            await util.send_success(ctx, "Starboard is now **enabled**")
        else:
            await util.send_success(ctx, "Starboard is now **disabled**")

    @starboard.command(name="emoji")
    async def starboard_emoji(self, ctx, emoji):
        """Change the emoji to use for starboard."""
        if emoji[0] == "<":
            # is custom emoji
            emoji_obj = await util.get_emoji(ctx, emoji)
            if emoji_obj is None:
                raise exceptions.Warning("I don't know this emoji!")

            await self.bot.db.execute(
                """
                INSERT INTO starboard_settings (guild_id, emoji_name, emoji_id, emoji_type)
                    VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    emoji_name = VALUES(emoji_name),
                    emoji_id = VALUES(emoji_id),
                    emoji_type = VALUES(emoji_type)
                """,
                ctx.guild.id,
                None,
                emoji_obj.id,
                "custom",
            )
            await util.send_success(
                ctx, f"Starboard emoji is now {emoji} (emoji id `{emoji_obj.id}`)"
            )
        else:
            # unicode emoji
            emoji_name = emoji_literals.UNICODE_TO_NAME.get(emoji)
            if emoji_name is None:
                raise exceptions.Warning("I don't know this emoji!")

            await self.bot.db.execute(
                """
                INSERT INTO starboard_settings (guild_id, emoji_name, emoji_id, emoji_type)
                    VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    emoji_name = VALUES(emoji_name),
                    emoji_id = VALUES(emoji_id),
                    emoji_type = VALUES(emoji_type)
                """,
                ctx.guild.id,
                emoji_name,
                None,
                "unicode",
            )
            await util.send_success(ctx, f"Starboard emoji is now {emoji}")

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def votechannel(self, ctx):
        """Configure voting channels."""
        await util.command_group_help(ctx)

    @votechannel.command(name="add")
    async def votechannel_add(self, ctx, channel: discord.TextChannel, reaction_type=None):
        """
        Set a channel to be a voting channel.

        Available types: [ vote | rate ]
        Defaults to vote.
        """
        if reaction_type is None:
            channel_type = "voting"
        elif reaction_type.lower() in ["rate", "rating"]:
            channel_type = "rating"
        elif reaction_type.lower() in ["vote", "voting"]:
            channel_type = "voting"
        else:
            raise exceptions.Warning(f"Unknown reaction type `{reaction_type}`", help_footer=True)

        await self.bot.db.execute(
            """
            INSERT INTO voting_channel (guild_id, channel_id, voting_type)
                VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                voting_type = VALUES(voting_type)
            """,
            ctx.guild.id,
            channel.id,
            channel_type,
        )
        self.bot.cache.votechannels.add(channel.id)
        await util.send_success(
            ctx, f"{channel.mention} is now a voting channel of type `{channel_type}`"
        )

    @votechannel.command(name="remove")
    async def votechannel_remove(self, ctx, *, channel: discord.TextChannel):
        """Remove a voting channel."""
        await self.bot.db.execute(
            "DELETE FROM voting_channel WHERE guild_id = %s and channel_id = %s",
            ctx.guild.id,
            channel.id,
        )
        self.bot.cache.votechannels.discard(channel.id)
        await util.send_success(ctx, f"{channel.mention} is no longer a voting channel.")

    @votechannel.command(name="list")
    async def votechannel_list(self, ctx):
        """List all current voting channels on this server."""
        channels = await self.bot.db.execute(
            """
            SELECT channel_id, voting_type FROM voting_channel WHERE guild_id = %s
            """,
            ctx.guild.id,
        )
        if not channels:
            raise exceptions.Info("There are no voting channels on this server yet!")

        rows = []
        for channel_id, voting_type in channels:
            rows.append(f"<#{channel_id}> - `{voting_type}`")

        content = discord.Embed(
            title=f":1234: Voting channels in {ctx.guild.name}", color=int("3b88c3", 16)
        )
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def muterole(self, ctx, *, role: discord.Role):
        """Set the mute role."""
        await queries.update_setting(ctx, "guild_settings", "mute_role_id", role.id)
        await util.send_success(ctx, f"Muting someone now gives them the role {role.mention}")

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx):
        """Configure roles to be given automatically to any new members."""
        await util.command_group_help(ctx)

    @autorole.command(name="add")
    async def autorole_add(self, ctx, *, role: discord.Role):
        """Add an autorole."""
        await self.bot.db.execute(
            "INSERT IGNORE autorole (guild_id, role_id) VALUES (%s, %s)", ctx.guild.id, role.id
        )
        await util.send_success(ctx, f"New members will now automatically get {role.mention}")

    @autorole.command(name="remove")
    async def autorole_remove(self, ctx, *, role):
        """Remove an autorole."""
        existing_role = await util.get_role(ctx, role)
        if existing_role is None:
            role_id = int(role)
        else:
            role_id = existing_role.id
        await self.bot.db.execute(
            "DELETE FROM autorole WHERE guild_id = %s AND role_id = %s", ctx.guild.id, role_id
        )
        await util.send_success(ctx, f"No longer giving new members <@&{role_id}>")

    @autorole.command(name="list")
    async def autorole_list(self, ctx):
        """List all current autoroles on this server."""
        roles = await self.bot.db.execute(
            "SELECT role_id FROM autorole WHERE guild_id = %s",
            ctx.guild.id,
            as_list=True,
        )
        content = discord.Embed(
            title=f":scroll: Autoroles in {ctx.guild.name}", color=int("ffd983", 16)
        )
        rows = []
        for role_id in roles:
            rows.append(f"<@&{role_id}> [`{role_id}`]")

        if not rows:
            rows = ["No roles have been set up yet!"]

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def autoresponses(self, ctx, value: bool):
        """Disable or enable automatic responses to certain message content."""
        await queries.update_setting(ctx, "guild_settings", "autoresponses", value)
        self.bot.cache.autoresponse[str(ctx.guild.id)] = value
        if value:
            await util.send_success(ctx, "Automatic responses are now **enabled**")
        else:
            await util.send_success(ctx, "Automatic responses are now **disabled**")


def setup(bot):
    bot.add_cog(Configuration(bot))
