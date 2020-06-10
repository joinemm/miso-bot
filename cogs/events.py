import discord
from discord.ext import commands, tasks
import helpers.log as log
import helpers.utilityfunctions as util
import data.database as db
import re
import random

logger = log.get_logger(__name__)


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stfu_regex = re.compile(
            r"(?:^|\W){0}(?:$|\W)".format("stfu"), flags=re.IGNORECASE
        )
        self.statuses = [
            ("watching", lambda: f"{len(self.bot.guilds)} servers"),
            ("listening", lambda: f"{len(set(self.bot.get_all_members()))} users"),
            ("playing", lambda: "misobot.xyz"),
        ]
        self.activities = {"playing": 0, "streaming": 1, "listening": 2, "watching": 3}
        self.current_status = None
        self.status_loop.start()

    def cog_unload(self):
        self.status_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        settings = db.get_from_data_json(["bot_settings"])
        self.logchannel = self.bot.get_channel(settings["log_channel"])
        self.emojis = {
            "upvote": self.bot.get_emoji(
                db.query("select id from emojis where name = 'upvote'")[0][0]
            ),
            "downvote": self.bot.get_emoji(
                db.query("select id from emojis where name = 'downvote'")[0][0]
            ),
        }

    @tasks.loop(minutes=3.0)
    async def status_loop(self):
        try:
            await self.next_status()
        except Exception as e:
            logger.error(e)

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_ready()
        logger.info("Starting status loop")

    async def next_status(self):
        """switch to the next status message"""
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
        await self.logchannel.send(embed=content)

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
        await self.logchannel.send(embed=content)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Called when a new member joins a guild."""
        channel_id = db.get_setting(member.guild.id, "welcome_channel")
        if channel_id is None:
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(
                f"Cannot welcome {member} to {member.guild.name} (invalid channel)"
            )

        message_format = db.get_setting(member.guild.id, "welcome_message")
        if message_format is None:
            message_format = "Welcome **{username}** {mention} to **{server}**"

        await channel.send(
            embed=util.create_welcome_embed(member, member.guild, message_format)
        )
        logger.info(f"Welcomed {member.name} to {member.guild.name}")

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

        await channel.send(f"**{user.name}** (`{user.id}`) has been permanently banned")
        logger.info(f"{user} was just banned from {guild.name}")

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

        await channel.send(
            util.create_goodbye_message(member, member.guild, message_format)
        )
        logger.info(f"Said goodbye to {member.name} from {member.guild.name}")

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
        # ignore DMs
        if message.guild is None:
            return

        # votechannels
        if (
            db.query(
                """SELECT * FROM votechannels
                WHERE guild_id = ? and channel_id = ?""",
                (message.guild.id, message.channel.id),
            )
            is not None
        ):
            await message.add_reaction(self.emojis.get("upvote"))
            await message.add_reaction(self.emojis.get("downvote"))

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

        # hi
        if (
            message.content.lower().strip("!.?~ ") == "hi"
            and random.randint(0, 19) == 0
        ):
            try:
                await message.channel.send("hi")
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
        if payload.emoji.name == "⭐":
            starboard_settings = db.query(
                """SELECT starboard_toggle, starboard_amount, starboard_channel
                FROM guilds WHERE guild_id = ?""",
                (payload.guild_id,),
            )
            if starboard_settings is None:
                # starboard not configured on this server
                return
            else:
                starboard_settings = starboard_settings[0]

            if not util.int_to_bool(starboard_settings[0]):
                return

            message = await self.bot.get_channel(payload.channel_id).fetch_message(
                payload.message_id
            )
            for react in message.reactions:
                if react.emoji == payload.emoji.name:
                    if react.count < starboard_settings[1]:
                        return
                    else:
                        reaction_count = react.count
                        break

            channel_id = starboard_settings[2]
            channel = payload.member.guild.get_channel(channel_id)
            if channel is None:
                return

            board_msg_id = db.query(
                """SELECT starboard_message_id FROM starboard WHERE message_id = ?""",
                (payload.message_id,),
            )
            try:
                board_message = await channel.fetch_message(board_msg_id[0][0])
            except (discord.errors.NotFound, TypeError):
                # message is not on board yet, or it was deleted
                content = discord.Embed(color=discord.Color.gold())
                content.set_author(
                    name=f"{message.author}", icon_url=message.author.avatar_url
                )
                jump = f"\n\n[context]({message.jump_url})"
                content.description = message.content[: 2048 - len(jump)] + jump
                content.timestamp = message.created_at
                content.set_footer(text=f"{reaction_count} ⭐ #{message.channel.name}")
                if len(message.attachments) > 0:
                    content.set_image(url=message.attachments[0].url)

                board_message = await channel.send(embed=content)
                db.execute(
                    "REPLACE INTO starboard VALUES(?, ?)",
                    (payload.message_id, board_message.id),
                )
            else:
                # message is on board, update star count
                content = board_message.embeds[0]
                content.set_footer(text=f"{reaction_count} ⭐ #{message.channel.name}")
                await board_message.edit(embed=content)


def setup(bot):
    bot.add_cog(Events(bot))
