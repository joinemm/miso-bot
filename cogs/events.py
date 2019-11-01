import discord
from discord.ext import commands
import helpers.log as log
import helpers.utilityfunctions as util
import data.database as db
import re
import random

logger = log.get_logger(__name__)


class Events(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.logchannel = 598783743959891968

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        logger.info(f"New guild : {guild}")
        channel = self.client.get_channel(self.logchannel)
        if channel is None:
            return logger.warning(f"Unable to get log channel!")

        content = discord.Embed(color=discord.Color.green())
        content.title = "New guild!"
        content.description = f"Miso just joined **{guild}**\nWith **{guild.member_count}** members"
        await channel.send(embed=content)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        logger.info(f"Left guild : {guild}")
        channel = self.client.get_channel(self.logchannel)
        if channel is None:
            return logger.warning(f"Unable to get log channel!")

        content = discord.Embed(color=discord.Color.red())
        content.title = "Left guild!"
        content.description = f"Miso just left **{guild}**\nWith **{guild.member_count}** members :("
        await channel.send(embed=content)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Called when a new member joins a server"""
        if not util.int_to_bool(db.get_setting(member.guild.id, "welcome_toggle")):
            return
            # return logger.info(f"{member.name} just joined {member.guild.name}, but welcome messages are disabled!")

        message_format = db.get_setting(member.guild.id, "welcome_message")
        if message_format is None:
            message_format = "Welcome **{username}** {mention} to **{server}**"
        channel_id = db.get_setting(member.guild.id, "welcome_channel")
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(f"Cannot welcome {member} to {member.guild.name} (welcome channel deleted)")

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
        """Called when user gets banned from a server"""
        if not util.int_to_bool(db.get_setting(guild.id, "welcome_toggle")):
            return
            # return logger.info(f"{user.name} just got banned from {guild.name}, but welcome messages are disabled!")

        channel_id = db.get_setting(guild.id, "welcome_channel")
        channel = guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(f"Cannot say goodbye to banned member {user} from {guild.name}")

        message = "**{name}** has been permanently banned"
        await channel.send(message.format(mention=user.mention, name=user.name))
        logger.info(f"{user.name} was just banned from {guild.name}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Called when member leaves a guild or is kicked"""
        if not util.int_to_bool(db.get_setting(member.guild.id, "welcome_toggle")):
            return
            # return logger.info(f"{member.name} just left {member.guild.name}, but welcome messages are disabled!")

        channel_id = db.get_setting(member.guild.id, "welcome_channel")
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return logger.warning(f"Cannot say goodbye to {member} from {member.guild.name}")

        await channel.send(f"Goodbye {member.mention} ( **{member.name}#{member.discriminator}** )")
        logger.info(f"Said goodbye to {member.name} from {member.guild.name}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listener that gets called on every message"""

        # ignore DMs
        if message.guild is None:
            return

        # votechannels
        if db.query("select * from votechannels where guild_id = ? and channel_id = ?",
                    (message.guild.id, message.channel.id)) is not None:
            await message.add_reaction(self.client.get_emoji(
                db.query("select id from emojis where name = 'upvote'")[0][0]))
            await message.add_reaction(self.client.get_emoji(
                db.query("select id from emojis where name = 'downvote'")[0][0]))

        # stfu
        pattern = re.compile(r'(?:^|\W){0}(?:$|\W)'.format('stfu'), flags=re.IGNORECASE)
        if not message.author.bot and pattern.findall(message.content) and random.randint(0, 2) == 0:
            await message.channel.send("no u")

        if message.content.lower().strip("!.?~ ") == "hi" and random.randint(0, 19) == 0:
            await message.channel.send('hi')

        # git gud
        if not message.author.bot and message.content.lower().startswith("git"):
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

        # xp gain
        message_xp = util.xp_from_message(message)
        currenthour = message.created_at.hour
        db.add_activity(message.guild.id, message.author.id, message_xp, currenthour)

        # leveups
        if not message.author.bot:
            announce = util.int_to_bool(db.get_setting(message.guild.id, "levelup_toggle"))
            if announce:
                activity_data = db.get_user_activity(message.guild.id, message.author.id)
                if activity_data is not None:
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

                channel_id = db.get_setting(reaction.message.guild.id, "starboard_channel")
                channel = reaction.message.guild.get_channel(channel_id)
                if channel is None:
                    logger.warning(f"Starboard channel not set for [{reaction.message.guild.name}]")
                    return

                board_msg_id = db.query("select starboard_message_id from starboard where message_id = ?",
                                        (reaction.message.id,))
                board_msg = await channel.fetch_message(board_msg_id) if board_msg_id is not None else None

                if board_msg is None:
                    if reaction.count == db.get_setting(reaction.message.guild.id, "starboard_amount"):
                        content = discord.Embed(color=discord.Color.gold())
                        content.set_author(name=f"{reaction.message.author}",
                                           icon_url=reaction.message.author.avatar_url)
                        jump = f"\n\n[context]({reaction.message.jump_url})"
                        content.description = reaction.message.content[:2048-len(jump)] + jump
                        content.timestamp = reaction.message.created_at
                        content.set_footer(text=f"{reaction.count} ⭐ #{reaction.message.channel.name}")
                        if len(reaction.message.attachments) > 0:
                            content.set_image(url=reaction.message.attachments[0].url)

                        msg = await channel.send(embed=content)
                        db.execute("INSERT INTO starboard values(?, ?)", (reaction.message.id, msg.id))
                else:
                    content = board_msg.embeds[0]
                    content.set_footer(text=f"{reaction.count} ⭐ #{reaction.message.channel.name}")
                    await board_msg.edit(embed=content)


def setup(client):
    client.add_cog(Events(client))
