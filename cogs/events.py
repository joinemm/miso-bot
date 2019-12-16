import discord
from discord.ext import commands
import helpers.log as log
import helpers.utilityfunctions as util
import data.database as db
import re
import random

logger = log.get_logger(__name__)


class Events(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.stfu_regex = re.compile(r'(?:^|\W){0}(?:$|\W)'.format('stfu'), flags=re.IGNORECASE)

    @commands.Cog.listener()
    async def on_ready(self):
        settings = db.get_from_data_json(['bot_settings'])
        self.logchannel = self.bot.get_channel(settings['log_channel'])
        activity_type, activity_text = settings['status']
        activities = {
            'playing': 0,
            'streaming': 1,
            'listening': 2,
            'watching': 3
        }

        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType(activities[activity_type]),
                name=activity_text
            )
        )
        logger.info(f"Changed presence to {activity_type} {activity_text}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Called when bot joins a new guild."""
        logger.info(f"New guild : {guild}")
        content = discord.Embed(color=discord.Color.green())
        content.title = "New guild!"
        content.description = f"Miso just joined **{guild}**\nWith **{guild.member_count-1}** members"
        content.set_thumbnail(url=guild.icon_url)
        content.set_footer(text=f"#{guild.id}")
        await self.logchannel.send(embed=content)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Called when bot leaves a guild."""
        logger.info(f"Left guild : {guild}")
        content = discord.Embed(color=discord.Color.red())
        content.title = "Left guild!"
        content.description = f"Miso just left **{guild}**\nWith **{guild.member_count-1}** members :("
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
            return logger.warning(f"Cannot welcome {member} to {member.guild.name} (invalid channel)")

        message_format = db.get_setting(member.guild.id, "welcome_message")
        if message_format is None:
            message_format = "Welcome **{username}** {mention} to **{server}**"
        
        await channel.send(embed=util.create_welcome_embed(member, member.guild, message_format))
        logger.info(f"Welcomed {member.name} to {member.guild.name}")

        # add autorole
        role = member.guild.get_role(db.get_setting(member.guild.id, "autorole"))
        if role is not None:
            try:
                await member.add_roles(role)
            except discord.errors.Forbidden:
                logger.error(f"Trying to add autorole failed in {member.guild.name} (no permissions)")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Called when user gets banned from a server."""
        channel_id = db.get_setting(guild.id, "bans_channel")
        if channel_id is None:
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(f"Cannot announce ban of {user} from {guild.name} (invalid channel)")

        await channel.send("**{user.name}** (`{user.id}`) has been permanently banned")
        logger.info(f"{user} was just banned from {guild.name}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Called when member leaves a guild."""
        channel_id = db.get_setting(member.guild.id, "goodbye_channel")
        if channel_id is None:
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(f"Cannot say goodbye to {member} from {member.guild.name} (invalid channel)")
        
        message_format = db.get_setting(member.guild.id, "goodbye_message")
        if message_format is None:
            message_format = "Goodbye {mention} ( **{user}** )"

        await channel.send(util.create_goodbye_message(member, member.guild, message_format))
        logger.info(f"Said goodbye to {member.name} from {member.guild.name}")
    
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Listener that gets called when any message is deleted."""
        # ignore DMs
        if message.guild is None:
            return
        
        channel_id = db.get_setting(message.guild.id, "deleted_messages_channel")
        if channel_id is None:
            return
        
        channel = message.guild.get_channel(channel_id)
        if channel is None:
            return
        
        await channel.send(embed=util.message_embed(message))

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listener that gets called on every message."""
        # ignore DMs
        if message.guild is None:
            return

        # votechannels
        if db.query("select * from votechannels where guild_id = ? and channel_id = ?",
                    (message.guild.id, message.channel.id)) is not None:
            await message.add_reaction(self.bot.get_emoji(
                db.query("select id from emojis where name = 'upvote'")[0][0]))
            await message.add_reaction(self.bot.get_emoji(
                db.query("select id from emojis where name = 'downvote'")[0][0]))

        # xp gain
        message_xp = util.xp_from_message(message)
        currenthour = message.created_at.hour
        db.add_activity(message.guild.id, message.author.id, message_xp, currenthour)
        
        # if bot account, ignore everything after this
        if message.author.bot:
            return
        
        # stfu
        if self.stfu_regex.findall(message.content) and random.randint(0, 1) == 0:
            await message.channel.send("no u")
        
        # hi
        if message.content.lower().strip("!.?~ ") == "hi" and random.randint(0, 19) == 0:
            await message.channel.send('hi')

        # git gud
        if message.content.lower().startswith("git "):
            gitcommand = re.search(r'git (\S+)', message.content)
            if gitcommand is not None:
                gitcommand = gitcommand.group(1)
                if gitcommand == "--help":
                    msg = "```\n" \
                          "usage: git [--version] [--help] [-C <path>] [-c <name>=<value>]\n" \
                          "           [--exec-path[=<path>]] [--html-path] [--man-path] [--info-path]\n" \
                          "           [-p | --paginate | --no-pager] [--no-replace-objects] [--bare]\n" \
                          "           [--git-dir=<path>] [--work-tree=<path>] [--namespace=<name>]\n" \
                          "           <command> [<args>]```"
                    await message.channel.send(msg)
                elif gitcommand == "--version":
                    await message.channel.send("`git version 2.17.1`")
                elif gitcommand in ["commit", "push", "pull", "checkout", "status", "init", "add"]:
                    pass
                else:
                    await message.channel.send(f"`git: '{gitcommand}' is not a git command. See 'git --help'.`")

        # log emojis
        unicode_emojis = util.find_unicode_emojis(message.content)
        custom_emojis = util.find_custom_emojis(message.content)
        if unicode_emojis or custom_emojis:
            db.log_emoji_usage(message, custom_emojis, unicode_emojis)

        # level up message
        announce = util.int_to_bool(db.get_setting(message.guild.id, "levelup_toggle"))
        if announce:
            activity_data = db.get_user_activity(message.guild.id, message.author.id)
            if activity_data is None:
                return

            xp = sum(activity_data)
            level_before = util.get_level(xp-message_xp)
            level_now = util.get_level(xp)

            if level_now > level_before:
                await message.channel.send(f"{message.author.mention} just leveled up! (level **{level_now}**)")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, _):
        """Starboard"""
        if reaction.emoji == "⭐":
            if util.int_to_bool(db.get_setting(reaction.message.guild.id, "starboard_toggle")):
                if reaction.count < db.get_setting(reaction.message.guild.id, "starboard_amount"):
                    return

                channel_id = db.get_setting(reaction.message.guild.id, "starboard_channel")
                channel = reaction.message.guild.get_channel(channel_id)
                if channel is None:
                    return logger.warning(f"Can't get starboard channel in {reaction.message.guild.name}")

                board_msg_id = db.query("select starboard_message_id from starboard where message_id = ?",
                                        (reaction.message.id,))

                if board_msg_id is None:
                    # message is not on board yet
                    content = discord.Embed(color=discord.Color.gold())
                    content.set_author(
                        name=f"{reaction.message.author}",
                        icon_url=reaction.message.author.avatar_url
                    )
                    jump = f"\n\n[context]({reaction.message.jump_url})"
                    content.description = reaction.message.content[:2048-len(jump)] + jump
                    content.timestamp = reaction.message.created_at
                    content.set_footer(text=f"{reaction.count} ⭐ #{reaction.message.channel.name}")
                    if len(reaction.message.attachments) > 0:
                        content.set_image(url=reaction.message.attachments[0].url)

                    msg = await channel.send(embed=content)
                    db.execute("INSERT INTO starboard values(?, ?)", (reaction.message.id, msg.id))

                else:
                    board_msg = await channel.fetch_message(board_msg_id[0][0])
                    content = board_msg.embeds[0]
                    content.set_footer(text=f"{reaction.count} ⭐ #{reaction.message.channel.name}")
                    await board_msg.edit(embed=content)


def setup(bot):
    bot.add_cog(Events(bot))
