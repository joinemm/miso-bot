import asyncio
import random

import arrow
import nextcord
from nextcord.ext import commands, tasks

from libraries import emoji_literals
from modules import emojis, log, queries, util

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()


class Events(commands.Cog):
    """Event handlers for various discord events"""

    def __init__(self, bot):
        self.bot = bot
        self.statuses = [
            ("watching", lambda: f"{len(self.bot.guilds):,} servers"),
            ("listening", lambda: f"{len(set(self.bot.get_all_members())):,} users"),
            ("playing", lambda: "misobot.xyz"),
        ]
        self.activities = {"playing": 0, "streaming": 1, "listening": 2, "watching": 3}
        self.xp_cache = {}
        self.emoji_usage_cache = {"unicode": {}, "custom": {}}
        self.current_status = None
        self.guildlog = 652916681299066900
        self.xp_limit = 150
        self.stats_messages = 0
        self.stats_reactions = 0
        self.stats_commands = 0
        self.bot.loop.create_task(self.start_tasks())

    def cog_unload(self):
        self.status_loop.cancel()

    async def start_tasks(self):
        """Start tasks."""
        await self.bot.wait_until_ready()
        self.status_loop.start()
        # self.xp_loop.start()
        # self.stats_loop.start()

    async def insert_stats(self):
        self.bot.logger.info("inserting usage stats")
        ts = arrow.now().floor("minute")
        await self.bot.db.execute(
            """
            INSERT INTO stats (
                ts, messages, reactions, commands_used,
                guild_count, member_count, notifications_sent,
                lastfm_api_requests, html_rendered
            )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                messages = messages + VALUES(messages),
                reactions = reactions + VALUES(reactions),
                commands_used = commands_used + VALUES(commands_used),
                guild_count = VALUES(guild_count),
                member_count = VALUES(member_count),
                notifications_sent = notifications_sent + values(notifications_sent),
                lastfm_api_requests = lastfm_api_requests + values(lastfm_api_requests),
                html_rendered = html_rendered + values(html_rendered)
            """,
            ts.datetime,
            self.stats_messages,
            self.stats_reactions,
            self.stats_commands,
            len(self.bot.guilds),
            len(set(self.bot.get_all_members())),
            self.bot.cache.stats_notifications_sent,
            self.bot.cache.stats_lastfm_requests,
            self.bot.cache.stats_html_rendered,
        )
        self.stats_messages = 0
        self.stats_reactions = 0
        self.stats_commands = 0
        self.bot.cache.stats_notifications_sent = 0
        self.bot.cache.stats_lastfm_requests = 0
        self.bot.cache.stats_html_rendered = 0

    async def write_usage_data(self):
        values = []
        total_messages = 0
        total_users = 0
        total_xp = 0
        for guild_id in self.xp_cache:
            for user_id, value in self.xp_cache[guild_id].items():
                xp = min(value["xp"], self.xp_limit)
                values.append(
                    (
                        int(guild_id),
                        int(user_id),
                        value["bot"],
                        xp,
                        value["messages"],
                    )
                )
                total_messages += value["messages"]
                total_xp += xp
                total_users += 1

        sql_tasks = []
        if values:
            currenthour = arrow.utcnow().hour
            for activity_table in [
                "user_activity",
                "user_activity_day",
                "user_activity_week",
                "user_activity_month",
            ]:
                sql_tasks.append(
                    self.bot.db.executemany(
                        f"""
                    INSERT INTO {activity_table} (guild_id, user_id, is_bot, h{currenthour}, message_count)
                        VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        h{currenthour} = h{currenthour} + VALUES(h{currenthour}),
                        message_count = message_count + VALUES(message_count)
                    """,
                        values,
                    )
                )
        self.xp_cache = {}

        unicode_emoji_values = []
        for guild_id in self.emoji_usage_cache["unicode"]:
            for user_id in self.emoji_usage_cache["unicode"][guild_id]:
                for emoji_name, value in self.emoji_usage_cache["unicode"][guild_id][
                    user_id
                ].items():
                    unicode_emoji_values.append((int(guild_id), int(user_id), emoji_name, value))

        if unicode_emoji_values:
            sql_tasks.append(
                self.bot.db.executemany(
                    """
                INSERT INTO unicode_emoji_usage (guild_id, user_id, emoji_name, uses)
                    VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    uses = uses + VALUES(uses)
                """,
                    unicode_emoji_values,
                )
            )
        self.emoji_usage_cache["unicode"] = {}

        custom_emoji_values = []
        for guild_id in self.emoji_usage_cache["custom"]:
            for user_id in self.emoji_usage_cache["custom"][guild_id]:
                for emoji_id, value in self.emoji_usage_cache["custom"][guild_id][user_id].items():
                    custom_emoji_values.append(
                        (
                            int(guild_id),
                            int(user_id),
                            value["name"],
                            emoji_id,
                            value["uses"],
                        )
                    )

        if custom_emoji_values:
            sql_tasks.append(
                self.bot.db.executemany(
                    """
                INSERT INTO custom_emoji_usage (guild_id, user_id, emoji_name, emoji_id, uses)
                    VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    uses = uses + VALUES(uses)
                """,
                    custom_emoji_values,
                )
            )
        self.emoji_usage_cache["custom"] = {}
        if sql_tasks:
            await asyncio.gather(*sql_tasks)
            logger.info(
                f"Inserted {total_messages} messages from {total_users} users, "
                f"average {total_messages/300:.2f} messages / second, {total_xp/total_users} xp per user"
            )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        """Runs when any command is completed succesfully."""
        # prevent double invocation for subcommands
        if ctx.invoked_subcommand is None:
            command_logger.info(log.log_command(ctx))
            self.stats_commands += 1
            if ctx.guild is not None:
                await queries.save_command_usage(ctx)

    @tasks.loop(minutes=5.0)
    async def xp_loop(self):
        try:
            await self.write_usage_data()
        except Exception as e:
            logger.error(f"xp_loop: {e}")

    @tasks.loop(minutes=3.0)
    async def status_loop(self):
        try:
            await self.next_status()
        except Exception as e:
            logger.error(f"next_status: {e}")

    @tasks.loop(minutes=1.0)
    async def stats_loop(self):
        try:
            await self.insert_stats()
        except Exception as e:
            logger.error(f"stats_loop: {e}")

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_ready()
        logger.info("Starting status loop")

    async def next_status(self):
        """switch to the next status message."""
        new_status_id = self.current_status
        while new_status_id == self.current_status:
            new_status_id = random.randrange(0, len(self.statuses))

        status = self.statuses[new_status_id]
        self.current_status = new_status_id

        await self.bot.change_presence(
            status=nextcord.Status.online,
            activity=nextcord.Activity(
                type=nextcord.ActivityType(self.activities[status[0]]), name=status[1]()
            ),
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Called when the bot joins a new guild."""
        self.bot.cache.event_triggers["guild_join"] += 1
        blacklisted = await self.bot.db.execute(
            "SELECT reason FROM blacklisted_guild WHERE guild_id = %s",
            guild.id,
            one_value=True,
        )
        if blacklisted:
            logger.info(f"Tried to join guild {guild}. Reason for blacklist: {blacklisted}")
            return await guild.leave()

        await self.bot.wait_until_ready()
        logger.info(f"New guild : {guild}")
        content = nextcord.Embed(color=nextcord.Color.green())
        content.title = "New guild!"
        content.description = (
            f"Miso just joined **{guild}**\nWith **{guild.member_count-1}** members"
        )
        content.set_thumbnail(url=guild.icon.url)
        content.set_footer(text=f"#{guild.id}")
        content.timestamp = arrow.utcnow().datetime
        logchannel = self.bot.get_channel(self.guildlog)
        await logchannel.send(embed=content)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Called when the bot leaves a guild."""
        self.bot.cache.event_triggers["guild_remove"] += 1
        # blacklisted = await self.bot.db.execute(
        #     "SELECT reason FROM blacklisted_guild WHERE guild_id = %s", guild.id, one_value=True
        # )
        # if blacklisted:
        #     return

        await self.bot.wait_until_ready()
        logger.info(f"Left guild {guild}")
        content = nextcord.Embed(color=nextcord.Color.red())
        content.title = "Left guild!"
        content.description = (
            f"Miso just left **{guild}**\nWith **{guild.member_count-1}** members :("
        )
        content.set_thumbnail(url=guild.icon.url)
        content.set_footer(text=f"#{guild.id}")
        content.timestamp = arrow.utcnow().datetime
        logchannel = self.bot.get_channel(self.guildlog)
        await logchannel.send(embed=content)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Called when a new member joins a guild."""
        self.bot.cache.event_triggers["member_join"] += 1
        # log event
        await self.bot.wait_until_ready()
        logging_channel_id = None
        logging_settings = self.bot.cache.logging_settings.get(str(member.guild.id))
        if logging_settings:
            logging_channel_id = logging_settings.get("member_log_channel_id")

        if logging_channel_id:
            logging_channel = member.guild.get_channel(logging_channel_id)
            if logging_channel is not None:
                embed = nextcord.Embed(color=nextcord.Color.green())
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                try:
                    await logging_channel.send(embed=embed)
                except nextcord.errors.Forbidden:
                    pass

        # add autoroles
        roles = self.bot.cache.autoroles.get(str(member.guild.id), [])
        for role_id in roles:
            role = member.guild.get_role(role_id)
            if role is None:
                continue
            try:
                await member.add_roles(role)
            except nextcord.errors.Forbidden:
                pass

        # welcome message
        greeter = await self.bot.db.execute(
            "SELECT channel_id, is_enabled, message_format FROM greeter_settings WHERE guild_id = %s",
            member.guild.id,
            one_row=True,
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
                    except nextcord.errors.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Called when user gets banned from a server."""
        self.bot.cache.event_triggers["member_ban"] += 1

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
                        embed=nextcord.Embed(
                            description=f":hammer: User banned **{user}** {user.mention}",
                            color=int("f4900c", 16),
                            timestamp=arrow.utcnow().datetime,
                        )
                    )
                except nextcord.errors.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_member_unban(self, *_):
        self.bot.cache.event_triggers["member_unban"] += 1

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Called when member leaves a guild."""
        if not self.bot.is_ready():
            return
        self.bot.cache.event_triggers["member_remove"] += 1
        # log event
        await self.bot.wait_until_ready()
        logging_channel_id = None
        logging_settings = self.bot.cache.logging_settings.get(str(member.guild.id))
        if logging_settings:
            logging_channel_id = logging_settings.get("member_log_channel_id")

        if logging_channel_id:
            logging_channel = member.guild.get_channel(logging_channel_id)
            if logging_channel is not None:
                embed = nextcord.Embed(color=nextcord.Color.red())
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                try:
                    await logging_channel.send(embed=embed)
                except nextcord.errors.Forbidden:
                    pass

        # goodbye message
        goodbye = await self.bot.db.execute(
            "SELECT channel_id, is_enabled, message_format FROM goodbye_settings WHERE guild_id = %s",
            member.guild.id,
            one_row=True,
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
                    except nextcord.errors.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        """Listener that gets called when any message is deleted."""
        if not self.bot.is_ready():
            return

        self.bot.cache.event_triggers["message_delete"] += 1

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
                ignored_channels = await self.bot.db.execute(
                    "SELECT channel_id FROM message_log_ignore WHERE guild_id = %s",
                    message.guild.id,
                    as_list=True,
                )
                if message.channel.id not in ignored_channels:
                    try:
                        await log_channel.send(embed=util.message_embed(message))
                    except nextcord.errors.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listener that gets called on every message."""
        if not self.bot.is_ready():
            return
        self.stats_messages += 1
        self.bot.cache.event_triggers["message"] += 1

        # temp fix
        return

        # ignore DMs
        if message.guild is None:
            return

        if message.channel.id in self.bot.cache.votechannels:
            # votechannels
            votechannel_type = await self.bot.db.execute(
                "SELECT voting_type FROM voting_channel WHERE channel_id = %s",
                message.channel.id,
                one_value=True,
            )
            if votechannel_type == "rating":
                for e in ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]:
                    await message.add_reaction(e)
            elif votechannel_type == "voting":
                await message.add_reaction(emojis.UPVOTE)
                await message.add_reaction(emojis.DOWNVOTE)

        # xp gain
        message_xp = util.xp_from_message(message)
        if self.xp_cache.get(str(message.guild.id)) is None:
            self.xp_cache[str(message.guild.id)] = {}
        try:
            self.xp_cache[str(message.guild.id)][str(message.author.id)]["xp"] += message_xp
            self.xp_cache[str(message.guild.id)][str(message.author.id)]["messages"] += 1
        except KeyError:
            self.xp_cache[str(message.guild.id)][str(message.author.id)] = {
                "xp": message_xp,
                "messages": 1,
                "bot": message.author.bot,
            }

        # if bot account, ignore everything after this
        if message.author.bot:
            return

        autoresponses = self.bot.cache.autoresponse.get(str(message.guild.id), True)

        # log emojis
        if self.bot.cache.log_emoji:
            unicode_emojis = util.find_unicode_emojis(message.content)
            custom_emojis = util.find_custom_emojis(message.content)

            for emoji_name in unicode_emojis:
                if self.emoji_usage_cache["unicode"].get(str(message.guild.id)) is None:
                    self.emoji_usage_cache["unicode"][str(message.guild.id)] = {}
                if (
                    self.emoji_usage_cache["unicode"][str(message.guild.id)].get(
                        str(message.author.id)
                    )
                    is None
                ):
                    self.emoji_usage_cache["unicode"][str(message.guild.id)][
                        str(message.author.id)
                    ] = {}
                try:
                    self.emoji_usage_cache["unicode"][str(message.guild.id)][
                        str(message.author.id)
                    ][emoji_name] += 1
                except KeyError:
                    self.emoji_usage_cache["unicode"][str(message.guild.id)][
                        str(message.author.id)
                    ][emoji_name] = 1

            for emoji_name, emoji_id in custom_emojis:
                if self.emoji_usage_cache["custom"].get(str(message.guild.id)) is None:
                    self.emoji_usage_cache["custom"][str(message.guild.id)] = {}
                if (
                    self.emoji_usage_cache["custom"][str(message.guild.id)].get(
                        str(message.author.id)
                    )
                    is None
                ):
                    self.emoji_usage_cache["custom"][str(message.guild.id)][
                        str(message.author.id)
                    ] = {}
                try:
                    self.emoji_usage_cache["custom"][str(message.guild.id)][
                        str(message.author.id)
                    ][str(emoji_id)]["uses"] += 1
                except KeyError:
                    self.emoji_usage_cache["custom"][str(message.guild.id)][
                        str(message.author.id)
                    ][str(emoji_id)] = {"uses": 1, "name": emoji_name}

        if autoresponses:
            await self.easter_eggs(message)

    async def easter_eggs(self, message):
        """Easter eggs handler."""
        # stfu
        if random.randint(0, 3) == 0 and "stfu" in message.content.lower():
            try:
                await message.channel.send("no u")
            except nextcord.errors.Forbidden:
                pass

        stripped_content = message.content.lower().strip("!.?~ ")

        # hi
        if stripped_content == "hi" and random.randint(0, 19) == 0:
            try:
                await message.channel.send("hi")
            except nextcord.errors.Forbidden:
                pass

        # hello there
        elif stripped_content == "hello there" and random.randint(0, 3) == 0:
            try:
                await message.channel.send("General Kenobi")
            except nextcord.errors.Forbidden:
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
                except nextcord.errors.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Starboard event handler."""
        if not self.bot.is_ready():
            return

        self.stats_reactions += 1
        self.bot.cache.event_triggers["reaction_add"] += 1
        user = self.bot.get_user(payload.user_id)
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
        if board_channel is None:
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

            # trying to star a starboard message
            if message_channel.id == board_channel_id:
                return
            try:
                message = await message_channel.fetch_message(payload.message_id)
            except (nextcord.errors.Forbidden, nextcord.errors.NotFound):
                return

            reaction_count = 0
            reacted_users = []
            for react in message.reactions:
                if emoji_type == "custom":
                    if (
                        isinstance(react.emoji, (nextcord.Emoji, nextcord.PartialEmoji))
                        and react.emoji.id == payload.emoji.id
                    ):
                        reaction_count = react.count
                        reacted_users = await react.users().flatten()
                        break
                else:
                    if react.emoji == payload.emoji.name:
                        reaction_count = react.count
                        reacted_users = await react.users().flatten()
                        break

            reacted_users = set(reacted_users)
            reacted_users.add(user)

            if reaction_count < required_reaction_count:
                return

            board_message_id = await self.bot.db.execute(
                "SELECT starboard_message_id FROM starboard_message WHERE original_message_id = %s",
                payload.message_id,
                one_value=True,
            )
            emoji_display = (
                "⭐" if emoji_type == "custom" else emoji_literals.NAME_TO_UNICODE[emoji_name]
            )

            board_message = None
            if board_message_id:
                try:
                    board_message = await board_channel.fetch_message(board_message_id)
                except nextcord.errors.NotFound:
                    pass

            if board_message is None:
                # message is not on board yet, or it was deleted
                content = nextcord.Embed(color=int("ffac33", 16))
                content.set_author(
                    name=f"{message.author}", icon_url=message.author.display_avatar.url
                )
                jump = f"\n\n[context]({message.jump_url})"
                content.description = message.content[: 2048 - len(jump)] + jump
                content.timestamp = message.created_at
                content.set_footer(
                    text=f"{reaction_count} {emoji_display} #{message.channel.name}"
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
                log_channel = self.bot.get_channel(log_channel_id)
                if log_channel is not None:
                    content = nextcord.Embed(
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
                    except Exception as e:
                        await log_channel.send(f"`error in starboard log: {e}`")

            else:
                # message is on board, update star count
                content = board_message.embeds[0]
                content.set_footer(
                    text=f"{reaction_count} {emoji_display} #{message.channel.name}"
                )
                await board_message.edit(embed=content)


def setup(bot):
    bot.add_cog(Events(bot))
