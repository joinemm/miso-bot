import discord
from discord.ext import commands
import data.database as db
import helpers.utilityfunctions as util
from libraries import unicode_codes


class ChannelSetting(commands.TextChannelConverter):
    """This enables removing a channel from the database in the same command that adds it."""

    async def convert(self, ctx, argument):
        if argument.lower() in ["disable", "none", "delete", "remove"]:
            return None
        else:
            return await super().convert(ctx, argument)


class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def prefix(self, ctx, prefix):
        """Set a custom command prefix for this server.

        Usage:
            >prefix <text>
            >prefix \"<text with spaces>\"
        """
        if prefix.strip() == "":
            return await ctx.send(":warning: Prefix cannot be empty.")
        elif prefix.startswith(" "):
            return await ctx.send(":warning: Prefix cannot start with a space.")
        elif len(prefix) > 32:
            return await ctx.send(":warning: Prefix cannot be over 32 characters.")

        prefix = prefix.lstrip()
        db.execute("REPLACE INTO prefixes VALUES (?, ?)", (ctx.guild.id, prefix))
        await ctx.send(
            f"Command prefix for this server set to `{prefix}`\n"
            f"Example command usage: {prefix}help"
        )

    @commands.group(name="logger")
    @commands.has_permissions(manage_channels=True)
    async def logmessages(self, ctx):
        """Configure the various event messages sent."""
        await util.command_group_help(ctx)

    @logmessages.group(name="welcome")
    async def logmessages_welcome(self, ctx):
        """Configure the welcome message."""
        await util.command_group_help(ctx)

    @logmessages_welcome.command(name="channel")
    async def welcome_channel(self, ctx, *, channel: ChannelSetting):
        """Set the welcome messages channel."""
        db.update_setting(
            ctx.guild.id, "welcome_channel", (None if channel is None else channel.id)
        )
        if channel is None:
            await ctx.send("Welcome messages disabled.")
        else:
            await ctx.send(f"Welcome channel set to {channel.mention}")

    @logmessages_welcome.command(name="message")
    async def welcome_message(self, ctx, *, message):
        """Change the welcome message.

        Usage:
            >logger welcome message <message...>
            >logger welcome message default
        """
        if message.lower() == "default":
            db.update_setting(ctx.guild.id, "welcome_message", None)
            return await ctx.send("Welcome message has been reset to default.")

        db.update_setting(ctx.guild.id, "welcome_message", message)

        if db.get_setting(ctx.guild.id, "welcome_embed") == 0:
            preview = util.create_welcome_without_embed(ctx.author, ctx.guild, message)
            await ctx.send(f"New welcome message set:\n```{message}```\n> Preview:")
            await ctx.send(preview)
        else:
            preview = util.create_welcome_embed(ctx.author, ctx.guild, message)
            await ctx.send(f"New welcome message set:\n```{message}```Preview:", embed=preview)

    @logmessages_welcome.command(name="embed")
    async def welcome_embed(self, ctx, state: bool):
        """Toggle whether welcome messages use embed or only text."""
        db.update_setting(ctx.guild.id, "welcome_embed", (1 if state else 0))
        await ctx.send(
            f"Welcome message embeds are now **{('enabled' if state else 'disabled')}**"
        )

    @logmessages.group(name="goodbye")
    async def logmessages_goodbye(self, ctx):
        """Configure the goodbye message."""
        await util.command_group_help(ctx)

    @logmessages_goodbye.command(name="channel")
    async def goodbye_channel(self, ctx, *, channel: ChannelSetting):
        """Set the goodbye messages channel."""
        db.update_setting(
            ctx.guild.id, "goodbye_channel", (None if channel is None else channel.id)
        )
        if channel is None:
            await ctx.send("Goodbye messages disabled.")
        else:
            await ctx.send(f"Goodbye channel set to {channel.mention}")

    @logmessages_goodbye.command(name="message")
    async def goodbye_message(self, ctx, *, message):
        """Change the goodbye message.

        Usage:
            >logger goodbye message <message...>
            >logger goodbye message default
        """
        if message.lower() == "default":
            db.update_setting(ctx.guild.id, "goodbye_message", None)
            return await ctx.send("Goodbye message has been reset to default.")

        db.update_setting(ctx.guild.id, "goodbye_message", message)
        await ctx.send(f"New Goodbye message set.\n```{message}```Preview:")
        await ctx.send(util.create_goodbye_message(ctx.author, ctx.guild, message))

    @logmessages.command(name="bans")
    async def logmessages_bans(self, ctx, *, channel: ChannelSetting):
        """Set channel where bans are announced."""
        db.update_setting(ctx.guild.id, "bans_channel", (None if channel is None else channel.id))
        if channel is None:
            await ctx.send("Ban messages disabled.")
        else:
            await ctx.send(f"Bans will now be logged in {channel.mention}")

    @logmessages.group(name="deleted")
    async def logmessages_deleted(self, ctx):
        """Configure deleted messages logging."""
        await util.command_group_help(ctx)

    @logmessages_deleted.command(name="channel")
    async def deleted_channel(self, ctx, *, channel: ChannelSetting):
        """Set channel where deleted messages are logged."""
        db.update_setting(
            ctx.guild.id, "deleted_messages_channel", (None if channel is None else channel.id),
        )
        if channel is None:
            await ctx.send("Deleted messages logs disabled.")
        else:
            await ctx.send(f"Deleted messages will now be logged in {channel.mention}")

    @logmessages_deleted.command(name="ignore")
    async def deleted_ignore(self, ctx, *, channel: discord.TextChannel):
        """Ignore channel from logging deleted messages."""
        db.execute(
            "insert or ignore into deleted_messages_mask values (?, ?)", (ctx.guild.id, channel.id)
        )
        await ctx.send(f"{channel.mention} is now ignored from message logging")

    @logmessages_deleted.command(name="unignore")
    async def deleted_unignore(self, ctx, *, channel: discord.TextChannel):
        """Unignore channel from logging deleted messages."""
        db.execute(
            "delete from deleted_messages_mask where guild_id = ? and channel_id = ?",
            (ctx.guild.id, channel.id),
        )
        await ctx.send(f"{channel.mention} is no longer ignored from message logging")

    @logmessages.command(name="levelups")
    async def logmessages_levelups(self, ctx, state: bool):
        """Enable or disable levelup messages."""
        db.update_setting(ctx.guild.id, "levelup_toggle", (1 if state else 0))
        await ctx.send(f"Levelup messages **{('enabled' if state else 'disabled')}**")

    @commands.group()
    @commands.has_permissions(manage_channels=True)
    async def starboard(self, ctx):
        """Configure the starboard."""
        await util.command_group_help(ctx)

    @starboard.command(name="channel")
    async def starboard_channel(self, ctx, channel: discord.TextChannel):
        """Set starboard channel"""
        db.update_setting(ctx.guild.id, "starboard_channel", channel.id)
        await ctx.send(f"Starboard channel set to {channel.mention}")

    @starboard.command(name="amount")
    async def starboard_amount(self, ctx, amount: int):
        """Change the amount of stars required"""
        db.update_setting(ctx.guild.id, "starboard_amount", amount)
        await ctx.send(f"Messages now need `{amount}` stars to get to the starboard.")

    @starboard.command(name="enable")
    async def starboard_enable(self, ctx):
        """Enable the starboard."""
        db.update_setting(ctx.guild.id, "starboard_toggle", 1)
        await ctx.send("Starboard **enabled**")

    @starboard.command(name="disable")
    async def starboard_disable(self, ctx):
        """Disable the starboard."""
        db.update_setting(ctx.guild.id, "starboard_toggle", 0)
        await ctx.send("Starboard **disabled**")

    @starboard.command(name="emoji")
    async def starboard_emoji(self, ctx, emoji):
        """Change the emoji to use for starboard."""
        if emoji[0] == "<":
            # is custom emoji
            emoji_obj = await util.get_emoji(ctx, emoji)
            if emoji_obj is None:
                return await ctx.send(":warning: I don't know this emoji!")

            db.update_setting(ctx.guild.id, "starboard_emoji_is_custom", 1)
            db.update_setting(ctx.guild.id, "starboard_emoji", emoji_obj.id)
            await ctx.send(
                f"Starboard emoji updated! Now looking for {emoji} reactions (emoji id `{emoji_obj.id}`)"
            )
        else:
            # unicode emoji
            if unicode_codes.UNICODE_EMOJI.get(emoji) is None:
                return await ctx.send(":warning: I don't know this emoji!")

            db.update_setting(ctx.guild.id, "starboard_emoji_is_custom", 0)
            db.update_setting(ctx.guild.id, "starboard_emoji", emoji)
            await ctx.send(f"Starboard emoji updated! Now looking for {emoji} reactions")

    @commands.group()
    @commands.has_permissions(manage_channels=True)
    async def votechannel(self, ctx):
        """Configure voting channels."""
        await util.command_group_help(ctx)

    @votechannel.command(name="add")
    async def votechannel_add(self, ctx, channel: discord.TextChannel, channeltype=None):
        """
        Set a channel to be a voting channel.

        Available types: [ vote | rate ]
        Defaults to vote
        """
        ctype = "rating" if channeltype.lower() == "rate" else None
        db.execute(
            "INSERT OR REPLACE INTO votechannels values(?, ?, ?)",
            (ctx.guild.id, channel.id, ctype),
        )
        await ctx.send(f"{channel.mention} is now a voting channel of type `{ctype or 'vote'}`")

    @votechannel.command(name="remove")
    async def votechannel_remove(self, ctx, *, channel: discord.TextChannel):
        """Remove voting channel."""
        if (
            db.query(
                "SELECT * FROM votechannels WHERE guild_id = ? and channel_id = ?",
                (ctx.guild.id, channel.id),
            )
            is None
        ):
            return await ctx.send(f":warning: {channel.mention} is not a voting channel!")

        db.execute(
            "DELETE FROM votechannels where guild_id = ? and channel_id = ?",
            (ctx.guild.id, channel.id),
        )
        await ctx.send(f"{channel.mention} is no longer a voting channel.")

    @votechannel.command(name="list")
    async def votechannel_list(self, ctx):
        """List all current voting channels."""
        channels = db.query(
            "select channel_id from votechannels where guild_id = ?", (ctx.guild.id,)
        )
        if channels is None:
            return await ctx.send("There are no voting channels on this server yet!")

        mentions = []
        for channel in channels:
            c = ctx.guild.get_channel(channel[0])
            if c is not None:
                mentions.append(c.mention)
            else:
                mentions.append(channel[0])

        content = discord.Embed(title=f"Voting channels in {ctx.guild.name}")
        content.description = "\n".join(mentions)
        await ctx.send(embed=content)

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def muterole(self, ctx, *, role):
        """Set the mute role.

        Usage:
            >muterole <role>
            >muterole remove
        """
        if role.lower() in ["none", "remove", "delete"]:
            db.update_setting(ctx.guild.id, "muterole", None)
            return await ctx.send("Muterole removed!")

        thisrole = await util.get_role(ctx, role)
        if thisrole is None:
            return await ctx.send(":warning: Unknown role")

        db.update_setting(ctx.guild.id, "muterole", thisrole.id)
        await ctx.send(
            embed=discord.Embed(description=f"Muting someone now gives them {thisrole.mention}")
        )

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx, *, role):
        """Set the role given automatically to new members.

        Usage:
            >autorole <role>
            >autorole remove
        """
        if role.lower() in ["none", "remove", "delete", "disable"]:
            db.update_setting(ctx.guild.id, "autorole", None)
            return await ctx.send("Autorole removed!")

        thisrole = await util.get_role(ctx, role)
        if thisrole is None:
            return await ctx.send(":warning: Unknown role")

        db.update_setting(ctx.guild.id, "autorole", thisrole.id)
        await ctx.send(
            embed=discord.Embed(
                description=f"New members will now automatically get {thisrole.mention}"
            )
        )

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def autoresponses(self, ctx, value: bool):
        """Disable/enable automatic responses to certain messages and easter eggs."""
        db.update_setting(ctx.guild.id, "autoresponses", util.bool_to_int(value))
        await ctx.send(f"Automatic message responses **{'enabled' if value else 'disabled'}**")


def setup(bot):
    bot.add_cog(Config(bot))
