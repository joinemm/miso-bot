import random
from itertools import cycle

import arrow
import discord
from discord.ext import commands, tasks
from loguru import logger

from libraries import emoji_literals
from modules import queries, util
from modules.misobot import MisoBot


class Events(commands.Cog):
    """Event handlers for various discord events"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.statuses = cycle(
            [
                ("watching", lambda: f"{self.bot.guild_count:,} servers"),
                ("listening", lambda: f"{self.bot.member_count:,} members"),
                ("playing", lambda: "misobot.xyz"),
            ]
        )
        self.activity_id = {"playing": 0, "streaming": 1, "listening": 2, "watching": 3}
        self.guildlog = 652916681299066900

    async def cog_load(self):
        self.status_loop.start()

    def cog_unload(self):
        self.status_loop.cancel()

    @tasks.loop(minutes=3.0)
    async def status_loop(self):
        await self.next_status()

    @status_loop.before_loop
    async def task_waiter(self):
        await self.bot.wait_until_ready()

    async def next_status(self):
        """switch to the next status message"""
        activity_type, status_func = next(self.statuses)
        await self.bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType(self.activity_id[activity_type]),
                name=status_func(),
            ),
        )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        """Runs when any command is completed succesfully"""
        # prevent double invocation for subcommands
        if ctx.invoked_subcommand is None:
            logger.info(util.log_command_format(ctx))
            if ctx.guild is not None:
                await queries.save_command_usage(ctx)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Called when the bot joins a new guild"""
        await self.bot.wait_until_ready()
        if not guild:
            return
        blacklisted = await self.bot.db.fetch_value(
            "SELECT reason FROM blacklisted_guild WHERE guild_id = %s",
            guild.id,
        )
        if blacklisted:
            logger.info(f"Tried to join guild {guild}. Reason for blacklist: {blacklisted}")
            return await guild.leave()

        logger.info(f"New guild : {guild}")
        content = discord.Embed(color=discord.Color.green())
        content.title = "New guild!"
        content.description = (
            f"Miso just joined **{guild}**\nWith **{guild.member_count}** members :D"
        )
        try:
            content.set_thumbnail(url=guild.icon.url)
        except AttributeError:
            pass
        content.set_footer(text=f"#{guild.id}")
        content.timestamp = arrow.utcnow().datetime
        logchannel = self.bot.get_partial_messageable(self.guildlog)
        try:
            await logchannel.send(embed=content)
        except (discord.Forbidden, discord.HTTPException):
            logger.error("Cannot send message to guild log channel")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Called when the bot leaves a guild"""
        await self.bot.wait_until_ready()
        if not guild:
            return
        logger.info(f"Left guild {guild}")
        content = discord.Embed(color=discord.Color.red())
        content.title = "Left guild!"
        content.description = (
            f"Miso just left **{guild}**\nWith **{guild.member_count}** members :("
        )
        try:
            content.set_thumbnail(url=guild.icon.url)
        except AttributeError:
            pass
        content.set_footer(text=f"#{guild.id}")
        content.timestamp = arrow.utcnow().datetime
        logchannel = self.bot.get_partial_messageable(self.guildlog)
        try:
            await logchannel.send(embed=content)
        except (discord.Forbidden, discord.HTTPException):
            logger.error("Cannot send message to guild log channel")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Called when a new member joins a guild"""
        await self.bot.wait_until_ready()
        logging_channel_id = None
        logging_settings = self.bot.cache.logging_settings.get(str(member.guild.id))
        if logging_settings:
            logging_channel_id = logging_settings.get("member_log_channel_id")

        if logging_channel_id:
            logging_channel = member.guild.get_channel(logging_channel_id)
            if logging_channel is not None:
                embed = discord.Embed(color=discord.Color.green())
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                try:
                    await logging_channel.send(embed=embed)
                except discord.errors.Forbidden:
                    pass

        # add autoroles
        roles = self.bot.cache.autoroles.get(str(member.guild.id), [])
        for role_id in roles:
            role = member.guild.get_role(role_id)
            if role is None:
                continue
            try:
                await member.add_roles(role)
            except discord.errors.Forbidden:
                pass

        # welcome message
        greeter = await self.bot.db.fetch_row(
            "SELECT channel_id, is_enabled, message_format FROM greeter_settings WHERE guild_id = %s",
            member.guild.id,
        )
        if greeter:
            channel_id, is_enabled, message_format = greeter
            if is_enabled:
                greeter_channel = member.guild.get_channel(channel_id)
                if greeter_channel is not None:
                    try:
                        await greeter_channel.send(
                            embed=util.create_welcome_embed(member, member.guild, message_format)
                        )
                    except discord.errors.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Called when user gets banned from a server"""
        await self.bot.wait_until_ready()
        logging_channel_id = None
        logging_settings = self.bot.cache.logging_settings.get(str(guild.id))
        if logging_settings:
            logging_channel_id = logging_settings.get("ban_log_channel_id")

        if logging_channel_id:
            channel = guild.get_channel(logging_channel_id)
            if channel is not None:
                try:
                    await channel.send(
                        embed=discord.Embed(
                            description=f":hammer: User banned **{user}** {user.mention}",
                            color=int("f4900c", 16),
                            timestamp=arrow.utcnow().datetime,
                        )
                    )
                except discord.errors.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Called when member leaves a guild"""
        await self.bot.wait_until_ready()
        logging_channel_id = None
        logging_settings = self.bot.cache.logging_settings.get(str(member.guild.id))
        if logging_settings:
            logging_channel_id = logging_settings.get("member_log_channel_id")

        if logging_channel_id:
            logging_channel = member.guild.get_channel(logging_channel_id)
            if logging_channel is not None:
                embed = discord.Embed(color=discord.Color.red())
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                try:
                    await logging_channel.send(embed=embed)
                except discord.errors.Forbidden:
                    pass

        # goodbye message
        goodbye = await self.bot.db.fetch_row(
            "SELECT channel_id, is_enabled, message_format FROM goodbye_settings WHERE guild_id = %s",
            member.guild.id,
        )
        if goodbye:
            channel_id, is_enabled, message_format = goodbye
            if is_enabled:
                channel = member.guild.get_channel(channel_id)
                if channel is not None:
                    if message_format is None:
                        message_format = "Goodbye **{user}** {mention}"

                    try:
                        await channel.send(
                            util.create_goodbye_message(member, member.guild, message_format)
                        )
                    except discord.errors.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        """Listener that gets called when any message is deleted"""
        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return

        message = payload.cached_message
        if message is None:
            return

        # ignore bots
        if message.author.bot:
            return

        # ignore DMs
        if message.guild is None:
            return

        # ignore empty messages
        if len(message.content) == 0 and len(message.attachments) == 0:
            return

        channel_id = None
        logging_settings = self.bot.cache.logging_settings.get(str(message.guild.id))
        if logging_settings:
            channel_id = logging_settings.get("message_log_channel_id")
        if channel_id:
            log_channel = message.guild.get_channel(channel_id)
            if log_channel is not None and message.channel != log_channel:
                # ignored channels
                ignored_channels = await self.bot.db.fetch_flattened(
                    "SELECT channel_id FROM message_log_ignore WHERE guild_id = %s",
                    message.guild.id,
                )
                if message.channel.id not in ignored_channels:
                    try:
                        await log_channel.send(embed=util.message_embed(message))
                    except discord.errors.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listener that gets called on every message"""
        await self.bot.wait_until_ready()

        # ignore DMs
        if message.guild is None:
            return

        # if bot account, ignore everything after this
        if message.author.bot:
            return

        autoresponses = self.bot.cache.autoresponse.get(str(message.guild.id), True)
        if autoresponses:
            await self.easter_eggs(message)

    @staticmethod
    async def easter_eggs(message):
        """Easter eggs handler"""
        # stfu
        if random.randint(1, 5) == 1 and "stfu" in message.content.lower():
            try:
                await message.channel.send("no u")
            except discord.errors.Forbidden:
                pass

        stripped_content = message.content.lower().strip("!.?~ ")

        # hi
        if stripped_content == "hi" and random.randint(1, 20) == 1:
            try:
                await message.channel.send("hi")
            except discord.errors.Forbidden:
                pass

        # hello there
        elif stripped_content == "hello there" and random.randint(1, 5) == 1:
            try:
                await message.channel.send("General Kenobi")
            except discord.errors.Forbidden:
                pass

        # git gud
        elif message.content.lower().startswith("git "):
            gitcommand = message.content.lower().split()[1].strip()
            if gitcommand == "--help":
                await message.channel.send("This is a joke.")
            elif gitcommand not in [
                "",
                "init",
                "reset",
                "rebase",
                "fetch",
                "commit",
                "push",
                "pull",
                "checkout",
                "status",
                "init",
                "add",
                "clone",
            ]:
                msg = f"`git: '{gitcommand}' is not a git command. See 'git --help'.`"
                try:
                    await message.channel.send(msg)
                except discord.errors.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Starboard event handler"""
        await self.bot.wait_until_ready()

        user = self.bot.get_user(payload.user_id)

        if not user:
            return

        if user.bot:
            return

        if payload.channel_id in self.bot.cache.starboard_blacklisted_channels:
            return

        starboard_settings = self.bot.cache.starboard_settings.get(str(payload.guild_id))
        if not starboard_settings:
            return

        (
            is_enabled,
            board_channel_id,
            required_reaction_count,
            emoji_name,
            emoji_id,
            emoji_type,
            log_channel_id,
        ) = starboard_settings

        if not is_enabled:
            return

        board_channel = self.bot.get_channel(board_channel_id)
        if not isinstance(board_channel, (discord.TextChannel, discord.Thread)):
            return

        if (
            emoji_type == "custom"
            and emoji_id is not None
            and payload.emoji.id is not None
            and payload.emoji.id == emoji_id
        ) or (
            (emoji_type == "unicode" or emoji_type is None)
            and emoji_literals.UNICODE_TO_NAME.get(payload.emoji.name) == emoji_name
        ):
            message_channel = self.bot.get_channel(payload.channel_id)
            if not isinstance(message_channel, (discord.TextChannel, discord.Thread)):
                return

            # trying to star a starboard message
            if message_channel.id == board_channel_id:
                return
            try:
                message = await message_channel.fetch_message(payload.message_id)
            except (discord.errors.Forbidden, discord.errors.NotFound):
                return

            reaction_count = 0
            reacted_users = []
            for react in message.reactions:
                if emoji_type == "custom":
                    if (
                        isinstance(react.emoji, (discord.Emoji, discord.PartialEmoji))
                        and react.emoji.id == payload.emoji.id
                    ):
                        reaction_count = react.count
                        reacted_users = [user async for user in react.users()]
                        break
                else:
                    if react.emoji == payload.emoji.name:
                        reaction_count = react.count
                        reacted_users = [user async for user in react.users()]
                        break

            reacted_users = set(reacted_users)
            reacted_users.add(user)

            if reaction_count < required_reaction_count:
                return

            board_message_id = await self.bot.db.fetch_value(
                "SELECT starboard_message_id FROM starboard_message WHERE original_message_id = %s",
                payload.message_id,
            )
            emoji_display = (
                "⭐" if emoji_type == "custom" else emoji_literals.NAME_TO_UNICODE[emoji_name]
            )

            board_message = None
            if isinstance(board_message_id, int):
                try:
                    board_message = await board_channel.fetch_message(board_message_id)
                except discord.errors.NotFound:
                    pass

            if board_message is None:
                # message is not on board yet, or it was deleted
                content = discord.Embed(color=int("ffac33", 16))
                content.set_author(
                    name=f"{message.author}", icon_url=message.author.display_avatar.url
                )
                jump = f"\n\n[context]({message.jump_url})"
                content.description = message.content[: 2048 - len(jump)] + jump
                content.timestamp = message.created_at
                content.set_footer(
                    text=f"{reaction_count} {emoji_display} {util.displaychannel(message.channel)}"
                )
                if len(message.attachments) > 0:
                    content.set_image(url=message.attachments[0].url)

                board_message = await board_channel.send(embed=content)
                await self.bot.db.execute(
                    """
                    INSERT INTO starboard_message (original_message_id, starboard_message_id)
                        VALUES(%s, %s)
                    ON DUPLICATE KEY UPDATE
                        starboard_message_id = VALUES(starboard_message_id)
                    """,
                    payload.message_id,
                    board_message.id,
                )
                log_channel = self.bot.get_partial_messageable(log_channel_id)
                if log_channel is not None:
                    content = discord.Embed(
                        color=int("ffac33", 16), title="Message added to starboard"
                    )
                    content.add_field(
                        name="Original message",
                        value=f"[{message.id}]({message.jump_url})",
                    )
                    content.add_field(
                        name="Board message",
                        value=f"[{board_message.id}]({board_message.jump_url})",
                    )
                    content.add_field(
                        name="Reacted users",
                        value="\n".join(str(x) for x in reacted_users)[:1023],
                        inline=False,
                    )
                    content.add_field(name="Most recent reaction by", value=str(user))
                    try:
                        await log_channel.send(embed=content)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            else:
                # message is on board, update star count
                content = board_message.embeds[0]
                content.set_footer(text=f"{reaction_count} {emoji_display} #{message.channel}")
                await board_message.edit(embed=content)


async def setup(bot):
    await bot.add_cog(Events(bot))
