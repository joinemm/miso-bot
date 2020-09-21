import discord
from discord.ext import commands, tasks
import helpers.log as log
import helpers.utilityfunctions as util
from helpers import emojis
import data.database as db
import re
import random
import asyncio

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stfu_regex = re.compile(r"(?:^|\W){0}(?:$|\W)".format("stfu"), flags=re.IGNORECASE)
        self.statuses = [
            ("watching", lambda: f"{len(self.bot.guilds)} servers"),
            ("listening", lambda: f"{len(set(self.bot.get_all_members()))} users"),
            ("playing", lambda: "misobot.xyz"),
        ]
        self.activities = {"playing": 0, "streaming": 1, "listening": 2, "watching": 3}
        self.current_status = None
        self.status_loop.start()
        self.settings = db.get_from_data_json(["bot_settings"])

    def cog_unload(self):
        self.status_loop.cancel()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        """Runs when any command is completed succesfully."""
        # prevent double invocation for subcommands
        if ctx.invoked_subcommand is None:
            command_logger.info(log.log_command(ctx))
            db.log_command_usage(ctx)

    @commands.Cog.listener()
    async def on_ready(self):
        """Runs when the bot connects to the discord servers."""
        # cache owner from appinfo
        self.bot.owner = (await self.bot.application_info()).owner
        latencies = self.bot.latencies
        logger.info(f"Loading complete | running {len(latencies)} shards")
        for shard_id, latency in latencies:
            logger.info(f"Shard [{shard_id}] - HEARTBEAT {latency}s")

    @tasks.loop(minutes=3.0)
    async def status_loop(self):
        try:
            await self.next_status()
        except Exception as e:
            logger.error(e)

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(30)  # avoid rate limit from discord in case of rapid reconnect
        logger.info("Starting status loop")

    async def next_status(self):
        """switch to the next status message."""
        new_status_id = self.current_status
        while new_status_id == self.current_status:
            new_status_id = random.randrange(0, len(self.statuses))

        status = self.statuses[new_status_id]
        self.current_status = new_status_id

        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType(self.activities[status[0]]), name=status[1]()
            )
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Called when bot joins a new guild."""
        logger.info(f"New guild : {guild}")
        content = discord.Embed(color=discord.Color.green())
        content.title = "New guild!"
        content.description = (
            f"Miso just joined **{guild}**\nWith **{guild.member_count-1}** members"
        )
        content.set_thumbnail(url=guild.icon_url)
        content.set_footer(text=f"#{guild.id}")
        logchannel = self.bot.get_channel(self.settings["log_channel"])
        await logchannel.send(embed=content)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Called when bot leaves a guild."""
        logger.info(f"Left guild : {guild}")
        content = discord.Embed(color=discord.Color.red())
        content.title = "Left guild!"
        content.description = (
            f"Miso just left **{guild}**\nWith **{guild.member_count-1}** members :("
        )
        content.set_thumbnail(url=guild.icon_url)
        content.set_footer(text=f"#{guild.id}")
        logchannel = self.bot.get_channel(self.settings["log_channel"])
        await logchannel.send(embed=content)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Called when a new member joins a guild."""
        channel_id = db.get_setting(member.guild.id, "welcome_channel")
        if channel_id is not None:
            channel = member.guild.get_channel(channel_id)
            if channel is None:
                logger.warning(f"Cannot welcome {member} to {member.guild.name} (invalid channel)")
            else:
                message_format = db.get_setting(member.guild.id, "welcome_message")
                if message_format is None:
                    message_format = "Welcome **{username}** {mention} to **{server}**"

                try:
                    if db.get_setting(member.guild.id, "welcome_embed") == 0:
                        await channel.send(
                            util.create_welcome_without_embed(member, member.guild, message_format)
                        )
                    else:
                        await channel.send(
                            embed=util.create_welcome_embed(member, member.guild, message_format)
                        )
                except discord.errors.Forbidden:
                    pass

        # add autorole
        role = member.guild.get_role(db.get_setting(member.guild.id, "autorole"))
        if role is not None:
            try:
                await member.add_roles(role)
            except discord.errors.Forbidden:
                logger.error(
                    f"Trying to add autorole failed in {member.guild.name} (no permissions)"
                )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Called when user gets banned from a server."""
        channel_id = db.get_setting(guild.id, "bans_channel")
        if channel_id is None:
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(
                f"Cannot announce ban of {user} from {guild.name} (invalid channel)"
            )

        try:
            await channel.send(f":hammer: **{user}** (`{user.id}`) has just been banned")
        except discord.errors.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Called when member leaves a guild."""
        channel_id = db.get_setting(member.guild.id, "goodbye_channel")
        if channel_id is None:
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(
                f"Cannot say goodbye to {member} from {member.guild.name} (invalid channel)"
            )

        message_format = db.get_setting(member.guild.id, "goodbye_message")
        if message_format is None:
            message_format = "Goodbye {mention} ( **{user}** )"

        try:
            await channel.send(util.create_goodbye_message(member, member.guild, message_format))
        except discord.errors.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Listener that gets called when any message is deleted."""
        # ignore bots
        if message.author.bot:
            return

        # ignore DMs
        if message.guild is None:
            return

        # ignore empty messages
        if len(message.content) == 0 and len(message.attachments) == 0:
            return

        # ignored channels
        if (
            db.query(
                "select * from deleted_messages_mask where channel_id = ?", (message.channel.id,),
            )
            is not None
        ):
            return

        channel_id = db.get_setting(message.guild.id, "deleted_messages_channel")
        if channel_id is None:
            return

        channel = message.guild.get_channel(channel_id)
        if channel is None or message.channel == channel:
            return

        try:
            await channel.send(embed=util.message_embed(message))
        except discord.errors.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listener that gets called on every message."""
        # make sure cache is ready
        if not self.bot.is_ready:
            return

        # ignore DMs
        if message.guild is None:
            return

        # votechannels

        data = db.query(
            """SELECT channeltype FROM votechannels
            WHERE guild_id = ? and channel_id = ?""",
            (message.guild.id, message.channel.id),
        )
        if data is not None:
            if data[0][0] == "rating":
                for e in ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]:
                    await message.add_reaction(e)
            else:
                await message.add_reaction(emojis.UPVOTE)
                await message.add_reaction(emojis.DOWNVOTE)

        # xp gain
        message_xp = util.xp_from_message(message)
        currenthour = message.created_at.hour
        db.add_activity(message.guild.id, message.author.id, message_xp, currenthour)

        # if bot account, ignore everything after this
        if message.author.bot:
            return

        if db.get_setting(message.guild.id, "autoresponses") == 1:
            await self.easter_eggs(message)

        # log emojis
        unicode_emojis = util.find_unicode_emojis(message.content)
        custom_emojis = util.find_custom_emojis(message.content)
        if unicode_emojis or custom_emojis:
            db.log_emoji_usage(message, custom_emojis, unicode_emojis)

        # level up message
        announce = db.get_setting(message.guild.id, "levelup_toggle")
        if announce != 0:
            activity_data = db.get_user_activity(message.guild.id, message.author.id)
            if activity_data is None:
                return

            xp = sum(activity_data)
            level_before = util.get_level(xp - message_xp)
            level_now = util.get_level(xp)

            if level_now > level_before:
                try:
                    await message.channel.send(
                        f"{message.author.mention} just leveled up! (level **{level_now}**)",
                        delete_after=5,
                    )
                except discord.errors.Forbidden:
                    pass

    async def easter_eggs(self, message):
        """Easter eggs handler."""
        # stfu
        if self.stfu_regex.findall(message.content) and random.randint(0, 1) == 0:
            try:
                await message.channel.send("no u")
            except discord.errors.Forbidden:
                pass

        stripped_content = message.content.lower().strip("!.?~ ")

        # hi
        if stripped_content == "hi" and random.randint(0, 19) == 0:
            try:
                await message.channel.send("hi")
            except discord.errors.Forbidden:
                pass

        # hello there
        elif stripped_content == "hello there" and random.randint(0, 2) == 0:
            try:
                await message.channel.send("General Kenobi")
            except discord.errors.Forbidden:
                pass

        # git gud
        if message.content.lower().startswith("git "):
            gitcommand = re.search(r"git (\S+)", message.content)
            if gitcommand is None:
                return
            gitcommand = gitcommand.group(1)
            if gitcommand == "--help":
                msg = (
                    "```\n"
                    "usage: git [--version] [--help] [-C <path>] [-c <name>=<value>]\n"
                    "           [--exec-path[=<path>]] [--html-path] [--man-path] [--info-path]\n"
                    "           [-p | --paginate | --no-pager] [--no-replace-objects] [--bare]\n"
                    "           [--git-dir=<path>] [--work-tree=<path>] [--namespace=<name>]\n"
                    "           <command> [<args>]```"
                )
            elif gitcommand == "--version":
                msg = "`git version 2.17.1`"
            elif gitcommand in [
                "commit",
                "push",
                "pull",
                "checkout",
                "status",
                "init",
                "add",
            ]:
                return
            else:
                msg = f"`git: '{gitcommand}' is not a git command. See 'git --help'.`"

            try:
                await message.channel.send(msg)
            except discord.errors.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Starboard event handler."""
        starboard_settings = db.query(
            """
            SELECT starboard_toggle, starboard_amount, starboard_channel, starboard_emoji, starboard_emoji_is_custom
            FROM guilds WHERE guild_id = ?""",
            (payload.guild_id,),
        )
        if starboard_settings is None:
            return
        else:
            starboard_settings = starboard_settings[0]

        if not util.int_to_bool(starboard_settings[0]):
            return

        custom_emoji = False
        if starboard_settings[3] is None:
            star_emoji = "⭐"
        else:
            star_emoji = starboard_settings[3]
            if starboard_settings[4] == 1:
                custom_emoji = True

        is_correct = False
        if custom_emoji and payload.emoji.id == int(star_emoji):
            is_correct = True
        elif payload.emoji.name == star_emoji:
            is_correct = True

        if is_correct:
            channel = self.bot.get_channel(payload.channel_id)
            if channel.id == starboard_settings[2]:
                # trying to star a starboard message
                return

            message = await channel.fetch_message(payload.message_id)
            for react in message.reactions:
                if custom_emoji:
                    if (
                        isinstance(react.emoji, (discord.Emoji, discord.PartialEmoji))
                        and react.emoji.id == payload.emoji.id
                    ):
                        reaction_count = react.count
                        break
                else:
                    if react.emoji == payload.emoji.name:
                        reaction_count = react.count
                        break

            if react.count < starboard_settings[1]:
                return

            channel_id = starboard_settings[2]
            channel = payload.member.guild.get_channel(channel_id)
            if channel is None:
                return

            board_msg_id = db.query(
                """SELECT starboard_message_id FROM starboard WHERE message_id = ?""",
                (payload.message_id,),
            )
            reaction_emoji = star_emoji if not custom_emoji else "⭐"
            try:
                assert board_msg_id is not None
                board_message = await channel.fetch_message(board_msg_id[0][0])
            except (discord.errors.NotFound, AssertionError):
                # message is not on board yet, or it was deleted
                content = discord.Embed(color=discord.Color.gold())
                content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
                jump = f"\n\n[context]({message.jump_url})"
                content.description = message.content[: 2048 - len(jump)] + jump
                content.timestamp = message.created_at
                content.set_footer(
                    text=f"{reaction_count} {reaction_emoji} #{message.channel.name}"
                )
                if len(message.attachments) > 0:
                    content.set_image(url=message.attachments[0].url)

                try:
                    board_message = await channel.send(embed=content)
                    db.execute(
                        "REPLACE INTO starboard VALUES(?, ?)",
                        (payload.message_id, board_message.id),
                    )
                except discord.errors.Forbidden:
                    logger.warning(
                        f"Unable to send message to starboard in {channel.guild} due to missing permissions!"
                    )

            else:
                # message is on board, update star count
                content = board_message.embeds[0]
                content.set_footer(
                    text=f"{reaction_count} {reaction_emoji} #{message.channel.name}"
                )
                await board_message.edit(embed=content)


def setup(bot):
    bot.add_cog(Events(bot))
