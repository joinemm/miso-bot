import discord
from discord.ext import commands

from libraries import emoji_literals
from modules import exceptions, queries, util


class ChannelSetting(commands.TextChannelConverter):
    """This enables removing a channel from the database in the same command that adds it"""

    async def convert(self, ctx: commands.Context, argument):
        if argument.lower() in ["disable", "none", "delete", "remove"]:
            return None
        return await super().convert(ctx, argument)


class Configuration(commands.Cog):
    """Configure how the bot behaves"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "⚙️"

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx: commands.Context, prefix):
        """
        Set a custom command prefix for this server

        Usage:
            >prefix <text>
            >prefix \"<text with spaces>\"
        """
        if prefix.strip() == "":
            raise exceptions.CommandWarning("Prefix cannot be empty.")

        if prefix.startswith(" "):
            raise exceptions.CommandWarning("Prefix cannot start with a space.")

        if len(prefix) > 32:
            raise exceptions.CommandWarning("Prefix cannot be over 32 characters.")

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
    async def greeter(self, ctx: commands.Context):
        """Set up welcome messages for new members"""
        await util.command_group_help(ctx)

    @greeter.command(name="toggle", aliases=["enabled"])
    async def greeter_toggle(self, ctx: commands.Context, value: bool):
        """Enable or disable the greeter"""
        await queries.update_setting(ctx, "greeter_settings", "is_enabled", value)
        if value:
            await util.send_success(ctx, "Greeter is now **enabled**")
        else:
            await util.send_success(ctx, "Greeter is now **disabled**")

    @greeter.command(name="channel")
    async def greeter_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Set the greeter channel"""
        await queries.update_setting(ctx, "greeter_settings", "channel_id", channel.id)
        await util.send_success(ctx, f"Greeter channel is now {channel.mention}")

    @greeter.command(name="message", usage="<message | default>")
    async def greeter_message(self, ctx: commands.Context, *, message):
        """
        Change the greeter welcome message format

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
    async def goodbyemessage(self, ctx: commands.Context):
        """Set up goodbye messages when members leave"""
        await util.command_group_help(ctx)

    @goodbyemessage.command(name="toggle", aliases=["enabled"])
    async def goodbye_toggle(self, ctx: commands.Context, value: bool):
        """Enable or disable the goodbye messages"""
        await queries.update_setting(ctx, "goodbye_settings", "is_enabled", value)
        if value:
            await util.send_success(ctx, "Goodbye messages are now **enabled**")
        else:
            await util.send_success(ctx, "Goodbye messages are now **disabled**")

    @goodbyemessage.command(name="channel")
    async def goodbye_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Set the goodbye message channel"""
        await queries.update_setting(ctx, "goodbye_settings", "channel_id", channel.id)
        await util.send_success(ctx, f"Goodbye messages channel is now {channel.mention}")

    @goodbyemessage.command(name="message", usage="<message | default>")
    async def goodbye_message(self, ctx: commands.Context, *, message):
        """
        Change the goodbye message format

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
    async def logger(self, ctx: commands.Context):
        """Configure the logging of various guild events"""
        await util.command_group_help(ctx)

    @logger.command(name="members", usage="<channel | none>")
    async def logger_members(self, ctx: commands.Context, *, channel: ChannelSetting):
        """
        Set channel for the membership log

        Set to \"none\" to disable.
        """
        await queries.update_setting(
            ctx,
            "logging_settings",
            "member_log_channel_id",
            channel.id if channel is not None else None,
        )
        await self.bot.cache.cache_logging_settings()
        if channel is None:
            await util.send_success(ctx, "Members logging **disabled**")
        else:
            await util.send_success(ctx, f"Member changes will now be logged to {channel.mention}")

    @logger.command(name="bans", usage="<channel | none>")
    async def logger_bans(self, ctx: commands.Context, *, channel: ChannelSetting):
        """
        Set channel where bans are logged

        Set to \"none\" to disable.
        """
        await queries.update_setting(
            ctx,
            "logging_settings",
            "ban_log_channel_id",
            channel.id if channel is not None else None,
        )
        await self.bot.cache.cache_logging_settings()
        if channel is None:
            await util.send_success(ctx, "Bans logging **disabled**")
        else:
            await util.send_success(ctx, f"Bans will now be logged to {channel.mention}")

    @logger.group(name="deleted")
    async def logger_deleted(self, ctx: commands.Context):
        """Configure logging of deleted messages"""
        await util.command_group_help(ctx)

    @logger_deleted.command(name="channel", usage="<channel | none>")
    async def deleted_channel(self, ctx: commands.Context, *, channel: ChannelSetting):
        """
        Set channel for message log

        Set to \"none\" to disable.
        """
        await queries.update_setting(
            ctx,
            "logging_settings",
            "message_log_channel_id",
            channel.id if channel is not None else None,
        )
        await self.bot.cache.cache_logging_settings()
        if channel is None:
            await util.send_success(ctx, "Deleted message logging **disabled**")
        else:
            await util.send_success(
                ctx, f"Deleted messages will now be logged to {channel.mention}"
            )

    @logger_deleted.command(name="ignore")
    async def deleted_ignore(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Ignore a channel from being logged in message log"""
        await self.bot.db.execute(
            "INSERT IGNORE message_log_ignore (guild_id, channel_id) VALUES (%s, %s)",
            ctx.guild.id,
            channel.id,
        )
        await util.send_success(
            ctx, f"No longer logging any messages deleted in {channel.mention}"
        )

    @logger_deleted.command(name="unignore")
    async def deleted_unignore(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Unignore a channel from being logged in message log"""
        await self.bot.db.execute(
            "DELETE FROM message_log_ignore WHERE guild_id = %s and channel_id = %s",
            ctx.guild.id,
            channel.id,
        )
        await util.send_success(
            ctx,
            f"{channel.mention} is no longer being ignored from deleted message logging.",
        )

    @commands.command(aliases=["levelups"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def levelup(self, ctx: commands.Context, value: bool):
        """Enable or disable levelup messages"""
        await queries.update_setting(ctx, "guild_settings", "levelup_messages", value)
        self.bot.cache.levelupmessage[str(ctx.guild.id)] = value
        if value:
            await util.send_success(ctx, "Level up messages are now **enabled**")
        else:
            await util.send_success(ctx, "Level up messages are now **disabled**")

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def starboard(self, ctx: commands.Context):
        """Configure the starboard"""
        await util.command_group_help(ctx)

    @starboard.command(name="channel")
    async def starboard_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the starboard channel"""
        await queries.update_setting(ctx, "starboard_settings", "channel_id", channel.id)
        await util.send_success(ctx, f"Starboard channel is now {channel.mention}")
        await self.bot.cache.cache_starboard_settings()

    @starboard.command(name="amount")
    async def starboard_amount(self, ctx: commands.Context, amount: int):
        """Change the amount of reactions required to starboard a message"""
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
            ctx,
            f"Messages now need **{amount}** {emoji} reactions to get into the starboard.",
        )
        await self.bot.cache.cache_starboard_settings()

    @starboard.command(name="toggle", aliases=["enabled"])
    async def starboard_toggle(self, ctx: commands.Context, value: bool):
        """Enable or disable the starboard"""
        await queries.update_setting(ctx, "starboard_settings", "is_enabled", value)
        if value:
            await util.send_success(ctx, "Starboard is now **enabled**")
        else:
            await util.send_success(ctx, "Starboard is now **disabled**")
        await self.bot.cache.cache_starboard_settings()

    @starboard.command(name="emoji")
    async def starboard_emoji(self, ctx: commands.Context, emoji):
        """Change the emoji to use for starboard"""
        if emoji[0] == "<":
            # is custom emoji
            emoji_obj = await util.get_emoji(ctx, emoji)
            if emoji_obj is None:
                raise exceptions.CommandWarning("I don't know this emoji!")

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
                raise exceptions.CommandWarning("I don't know this emoji!")

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
        await self.bot.cache.cache_starboard_settings()

    @starboard.command(name="log", usage="<channel | none>")
    async def starboard_log(self, ctx: commands.Context, channel: ChannelSetting):
        """Set starboard logging channel to log starring events"""
        if channel is None:
            await queries.update_setting(ctx, "starboard_settings", "log_channel_id", None)
            await util.send_success(ctx, "Starboard log is now disabled")
        else:
            await queries.update_setting(ctx, "starboard_settings", "log_channel_id", channel.id)
            await util.send_success(ctx, f"Starboard log channel is now {channel.mention}")
        await self.bot.cache.cache_starboard_settings()

    @starboard.command(name="blacklist")
    async def starboard_blacklist(self, ctx: commands.Context, channel: discord.TextChannel):
        """Blacklist a channel from being counted for starboard"""
        await self.bot.db.execute(
            """
            INSERT INTO starboard_blacklist (guild_id, channel_id)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                channel_id = channel_id
            """,
            ctx.guild.id,
            channel.id,
        )
        await util.send_success(ctx, f"Stars are no longer counted in {channel.mention}")
        await self.bot.cache.cache_starboard_settings()

    @starboard.command(name="unblacklist")
    async def starboard_unblacklist(self, ctx: commands.Context, channel: discord.TextChannel):
        """Unblacklist a channel from being counted for starboard"""
        await self.bot.db.execute(
            """
            DELETE FROM starboard_blacklist WHERE guild_id = %s AND channel_id = %s
            """,
            ctx.guild.id,
            channel.id,
        )
        await util.send_success(ctx, f"Stars are now again counted in {channel.mention}")
        await self.bot.cache.cache_starboard_settings()

    @starboard.command(name="current")
    async def starboard_current(self, ctx: commands.Context):
        """See the current starboard configuration"""
        starboard_settings = self.bot.cache.starboard_settings.get(str(ctx.guild.id))
        if not starboard_settings:
            raise exceptions.CommandWarning("Nothing has been configured on this server yet!")

        (
            is_enabled,
            board_channel_id,
            required_reaction_count,
            emoji_name,
            emoji_id,
            emoji_type,
            log_channel_id,
        ) = starboard_settings

        if emoji_type == "custom":
            emoji = self.bot.get_emoji(emoji_id)
        else:
            emoji = emoji_name

        blacklisted_channels = await self.bot.db.execute(
            """
            SELECT channel_id FROM starboard_blacklist WHERE guild_id = %s
            """,
            ctx.guild.id,
            as_list=True,
        )

        content = discord.Embed(title=":star: Current starboard settings", color=int("ffac33", 16))
        content.add_field(
            name="State",
            value=":white_check_mark: Enabled" if is_enabled else ":x: Disabled",
        )
        content.add_field(name="Emoji", value=emoji)
        content.add_field(name="Reactions required", value=required_reaction_count)
        content.add_field(
            name="Board channel",
            value=f"<#{board_channel_id}>" if board_channel_id is not None else None,
        )
        content.add_field(
            name="Log channel",
            value=f"<#{log_channel_id}>" if log_channel_id is not None else None,
        )
        content.add_field(
            name="Blacklisted channels",
            value=" ".join(f"<#{cid}>" for cid in blacklisted_channels)
            if blacklisted_channels
            else None,
        )

        await ctx.send(embed=content)

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def votechannel(self, ctx: commands.Context):
        """Configure voting channels"""
        await util.command_group_help(ctx)

    @votechannel.command(name="add")
    async def votechannel_add(
        self, ctx: commands.Context, channel: discord.TextChannel, reaction_type=None
    ):
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
            raise exceptions.CommandWarning(
                f"Unknown reaction type `{reaction_type}`", help_footer=True
            )

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
    async def votechannel_remove(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Remove a voting channel"""
        await self.bot.db.execute(
            "DELETE FROM voting_channel WHERE guild_id = %s and channel_id = %s",
            ctx.guild.id,
            channel.id,
        )
        self.bot.cache.votechannels.discard(channel.id)
        await util.send_success(ctx, f"{channel.mention} is no longer a voting channel.")

    @votechannel.command(name="list")
    async def votechannel_list(self, ctx: commands.Context):
        """List all current voting channels on this server"""
        channels = await self.bot.db.execute(
            """
            SELECT channel_id, voting_type FROM voting_channel WHERE guild_id = %s
            """,
            ctx.guild.id,
        )
        if not channels:
            raise exceptions.CommandInfo("There are no voting channels on this server yet!")

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
    async def muterole(self, ctx: commands.Context, *, role: discord.Role):
        """Set the role given when muting people using the mute command"""
        await queries.update_setting(ctx, "guild_settings", "mute_role_id", role.id)
        await util.send_success(ctx, f"Muting someone now gives them the role {role.mention}")

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx: commands.Context):
        """Configure roles to be given automatically to any new members"""
        await util.command_group_help(ctx)

    @autorole.command(name="add")
    async def autorole_add(self, ctx: commands.Context, *, role: discord.Role):
        """Add an autorole"""
        await self.bot.db.execute(
            "INSERT IGNORE autorole (guild_id, role_id) VALUES (%s, %s)",
            ctx.guild.id,
            role.id,
        )
        await util.send_success(ctx, f"New members will now automatically get {role.mention}")

    @autorole.command(name="remove")
    async def autorole_remove(self, ctx: commands.Context, *, role):
        """Remove an autorole"""
        existing_role = await util.get_role(ctx, role)
        if existing_role is None:
            role_id = int(role)
        else:
            role_id = existing_role.id
        await self.bot.db.execute(
            "DELETE FROM autorole WHERE guild_id = %s AND role_id = %s",
            ctx.guild.id,
            role_id,
        )
        await self.bot.cache.cache_autoroles()
        await util.send_success(ctx, f"No longer giving new members <@&{role_id}>")

    @autorole.command(name="list")
    async def autorole_list(self, ctx: commands.Context):
        """List current autoroles"""
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
    async def autoresponses(self, ctx: commands.Context, value: bool):
        """Disable or enable automatic responses to certain message content"""
        await queries.update_setting(ctx, "guild_settings", "autoresponses", value)
        self.bot.cache.autoresponse[str(ctx.guild.id)] = value
        if value:
            await util.send_success(ctx, "Automatic responses are now **enabled**")
        else:
            await util.send_success(ctx, "Automatic responses are now **disabled**")

    @commands.group()
    async def blacklist(self, ctx: commands.Context):
        """Restrict command usage"""
        await util.command_group_help(ctx)

    @blacklist.command(name="delete")
    @commands.has_permissions(manage_guild=True)
    async def blacklist_delete(self, ctx: commands.Context, value: bool):
        """Toggle whether to delete the message on blacklist trigger"""
        await queries.update_setting(ctx, "guild_settings", "delete_blacklisted_usage", value)
        if value:
            await util.send_success(ctx, "Now deleting messages that trigger any blacklists.")
        else:
            await util.send_success(ctx, "No longer deleting messages that trigger blacklists.")

    @blacklist.command(name="show")
    @commands.has_permissions(manage_guild=True)
    async def blacklist_show(self, ctx: commands.Context):
        """Show everything that's currently blacklisted"""
        content = discord.Embed(
            title=f":scroll: {ctx.guild.name} Blacklist", color=int("ffd983", 16)
        )

        blacklisted_channels = await self.bot.db.execute(
            """
            SELECT channel_id FROM blacklisted_channel WHERE guild_id = %s
            """,
            ctx.guild.id,
            as_list=True,
        )
        blacklisted_members = await self.bot.db.execute(
            """
            SELECT user_id FROM blacklisted_member WHERE guild_id = %s
            """,
            ctx.guild.id,
            as_list=True,
        )
        blacklisted_commands = await self.bot.db.execute(
            """
            SELECT command_name FROM blacklisted_command WHERE guild_id = %s
            """,
            ctx.guild.id,
            as_list=True,
        )

        def length_limited_value(rows):
            value = ""
            for row in rows:
                if len(value + "\n" + row) > 1019:
                    value += "\n..."
                    break

                value += ("\n" if value != "" else "") + row

            return value

        if blacklisted_channels:
            rows = [f"<#{channel_id}>" for channel_id in blacklisted_channels]
            content.add_field(
                name="Channels",
                value=length_limited_value(rows),
            )
        if blacklisted_members:
            rows = [f"<@{user_id}>" for user_id in blacklisted_members]
            content.add_field(
                name="Users",
                value=length_limited_value(rows),
            )
        if blacklisted_commands:
            rows = [f"`{ctx.prefix}{command}`" for command in blacklisted_commands]
            content.add_field(
                name="Commands",
                value=length_limited_value(rows),
            )

        if not content.fields:
            content.description = "Nothing is blacklisted yet!"

        await ctx.send(embed=content)

    @blacklist.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def blacklist_channel(self, ctx: commands.Context, *channels):
        """Blacklist a channel"""
        successes = []
        fails = []
        for channel_arg in channels:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, channel_arg)
            except commands.errors.BadArgument:
                fails.append(f"Cannot find channel {channel_arg}")
            else:
                await self.bot.db.execute(
                    """
                    INSERT INTO blacklisted_channel (channel_id, guild_id)
                        VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE
                        channel_id = VALUES(channel_id)
                    """,
                    channel.id,
                    ctx.guild.id,
                )
                self.bot.cache.blacklist["global"]["channel"].add(channel.id)
                successes.append(f"Blacklisted {channel.mention}")

        await util.send_tasks_result_list(ctx, successes, fails)

    @blacklist.command(name="member")
    @commands.has_permissions(manage_guild=True)
    async def blacklist_member(self, ctx: commands.Context, *members):
        """Blacklist a member of this server"""
        successes = []
        fails = []
        for member_arg in members:
            try:
                member = await commands.MemberConverter().convert(ctx, member_arg)
            except commands.errors.BadArgument:
                fails.append(f"Cannot find member {member_arg}")
            else:
                if member == ctx.author:
                    fails.append("You cannot blacklist yourself!")
                    continue

                await self.bot.db.execute(
                    """
                    INSERT INTO blacklisted_member (user_id, guild_id)
                        VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE
                        user_id = VALUES(user_id)
                    """,
                    member.id,
                    ctx.guild.id,
                )
                try:
                    self.bot.cache.blacklist[str(ctx.guild.id)]["member"].add(member.id)
                except KeyError:
                    self.bot.cache.blacklist[str(ctx.guild.id)] = {
                        "member": {member.id},
                        "command": set(),
                    }
                successes.append(f"Blacklisted {member.mention}")

        await util.send_tasks_result_list(ctx, successes, fails)

    @blacklist.command(name="command")
    @commands.has_permissions(manage_guild=True)
    async def blacklist_command(self, ctx: commands.Context, *, command):
        """Blacklist a command"""
        cmd = self.bot.get_command(command)
        if cmd is None:
            raise exceptions.CommandWarning(f"Command `{ctx.prefix}{command}` not found.")

        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_command VALUES (%s, %s)",
            cmd.qualified_name,
            ctx.guild.id,
        )
        try:
            self.bot.cache.blacklist[str(ctx.guild.id)]["command"].add(cmd.qualified_name.lower())
        except KeyError:
            self.bot.cache.blacklist[str(ctx.guild.id)] = {
                "member": set(),
                "command": {cmd.qualified_name.lower()},
            }
        await util.send_success(
            ctx, f"`{ctx.prefix}{cmd}` is now a blacklisted command on this server."
        )

    @blacklist.command(name="global", hidden=True)
    @commands.is_owner()
    async def blacklist_global(self, ctx: commands.Context, user: discord.User, *, reason):
        """Blacklist someone globally from Miso Bot"""
        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_user VALUES (%s, %s)", user.id, reason
        )
        self.bot.cache.blacklist["global"]["user"].add(user.id)
        await util.send_success(ctx, f"**{user}** can no longer use Miso Bot!")

    @blacklist.command(name="guild", hidden=True)
    @commands.is_owner()
    async def blacklist_guild(self, ctx: commands.Context, guild_id: int, *, reason):
        """Blacklist a guild from adding or using Miso Bot"""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise exceptions.CommandWarning(f"Cannot find guild with id `{guild_id}`")

        await self.bot.db.execute(
            "INSERT IGNORE blacklisted_guild VALUES (%s, %s)", guild.id, reason
        )
        self.bot.cache.blacklist["global"]["guild"].add(guild_id)
        await guild.leave()
        await util.send_success(ctx, f"**{guild}** can no longer use Miso Bot!")

    @commands.group(aliases=["whitelist"])
    async def unblacklist(self, ctx: commands.Context):
        """Reverse blacklisting"""
        await util.command_group_help(ctx)

    @unblacklist.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def unblacklist_channel(self, ctx: commands.Context, *channels):
        """Unblacklist a channel"""
        successes = []
        fails = []
        for channel_arg in channels:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, channel_arg)
            except commands.errors.BadArgument:
                fails.append(f"Cannot find channel {channel_arg}")
            else:
                await self.bot.db.execute(
                    "DELETE FROM blacklisted_channel WHERE guild_id = %s AND channel_id = %s",
                    ctx.guild.id,
                    channel.id,
                )
                self.bot.cache.blacklist["global"]["channel"].discard(channel.id)
                successes.append(f"Unblacklisted {channel.mention}")

        await util.send_tasks_result_list(ctx, successes, fails)

    @unblacklist.command(name="member")
    @commands.has_permissions(manage_guild=True)
    async def unblacklist_member(self, ctx: commands.Context, *members):
        """Unblacklist a member of this server"""
        successes = []
        fails = []
        for member_arg in members:
            try:
                member = await commands.MemberConverter().convert(ctx, member_arg)
            except commands.errors.BadArgument:
                fails.append(f"Cannot find member {member_arg}")
            else:
                await self.bot.db.execute(
                    "DELETE FROM blacklisted_member WHERE guild_id = %s AND user_id = %s",
                    ctx.guild.id,
                    member.id,
                )
                self.bot.cache.blacklist[str(ctx.guild.id)]["member"].discard(member.id)
                successes.append(f"Unblacklisted {member.mention}")

        await util.send_tasks_result_list(ctx, successes, fails)

    @unblacklist.command(name="command")
    @commands.has_permissions(manage_guild=True)
    async def unblacklist_command(self, ctx: commands.Context, *, command):
        """Unblacklist a command"""
        cmd = self.bot.get_command(command)
        if cmd is None:
            raise exceptions.CommandWarning(f"Command `{ctx.prefix}{command}` not found.")

        await self.bot.db.execute(
            "DELETE FROM blacklisted_command WHERE guild_id = %s AND command_name = %s",
            ctx.guild.id,
            cmd.qualified_name,
        )
        self.bot.cache.blacklist[str(ctx.guild.id)]["command"].discard(cmd.qualified_name.lower())
        await util.send_success(ctx, f"`{ctx.prefix}{cmd}` is no longer blacklisted.")

    @unblacklist.command(name="global", hidden=True)
    @commands.is_owner()
    async def unblacklist_global(self, ctx: commands.Context, *, user: discord.User):
        """Unblacklist someone globally"""
        await self.bot.db.execute("DELETE FROM blacklisted_user WHERE user_id = %s", user.id)
        self.bot.cache.blacklist["global"]["user"].discard(user.id)
        await util.send_success(ctx, f"**{user}** can now use Miso Bot again!")

    @unblacklist.command(name="guild", hidden=True)
    @commands.is_owner()
    async def Unblacklist_guild(self, ctx: commands.Context, guild_id: int):
        """unblacklist a guild"""
        await self.bot.db.execute("DELETE FROM blacklisted_guild WHERE guild_id = %s", guild_id)
        self.bot.cache.blacklist["global"]["guild"].discard(guild_id)
        await util.send_success(ctx, f"Guild with id `{guild_id}` can use Miso Bot again!")


async def setup(bot):
    await bot.add_cog(Configuration(bot))
