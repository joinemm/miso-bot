import discord
from discord.ext import commands
import helpers.log as log
import helpers.utilityfunctions as util
import data.database as db
import re

logger = log.get_logger(__name__)
command_logger = log.get_command_logger()


class Events(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command()
    async def test(self, ctx, *args):
        await ctx.send(" ".join(args))

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listened that gets called on every message"""

        # ignore DMs
        if message.guild is None:
            return

        # votechannels
        if db.query("select * from votechannels where guild_id = ? and channel_id = ?",
                    (message.guild.id, message.channel.id)) is not None:
            await message.add_reaction(self.client.get_emoji(540246030491451392))
            await message.add_reaction(self.client.get_emoji(540246041962872852))

        # miso was pinged
        if not message.author.bot and self.client.user in message.mentions:
            await message.channel.send("<:misoping:532922215105036329>")

        # git gud
        if not message.author.bot and message.content.lower().startswith("git"):
            gitcommand = re.search(r'git (\S+)', message.content).group(1)
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

        # notifications
        keywords = db.get_keywords(message.guild.id)
        print(keywords)
        if keywords is not None:
            for (word, user_id) in keywords:
                if user_id == message.author.id:
                    continue
                pattern = re.compile(r'(?:^|\W){0}(?:$|\W)'.format(word), flags=re.IGNORECASE)
                if pattern.findall(message.content):
                    user = message.guild.get_member(user_id)
                    if user is None:
                        continue
                    if user not in message.channel.members:
                        continue

                    # create and send notification message
                    content = discord.Embed()
                    content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
                    highlighted_text = re.sub(pattern, lambda x: f'**{x.group(0)}**', message.content)
                    content.description = f"`>>>` {highlighted_text}\n\n" \
                                          f"[Go to message]({message.jump_url})"
                    content.set_footer(text=f"{message.guild.name} | #{message.channel.name}")
                    content.timestamp = message.created_at

                    await user.send(embed=content)

        # xp gain
        message_xp = util.xp_from_message(message)
        currenthour = message.created_at.hour
        db.add_activity(message.guild.id, message.author.id, message_xp, currenthour)

        if not message.author.bot:
            announce = True if db.get_setting(message.guild.id, "levelup_toggle") == 1 else False
            if announce:
                activity_data = db.activitydata(message.guild.id, message.author.id)
                level_before = util.get_level(activity_data.xp-message_xp)
                level_now = util.get_level(activity_data.xp)

                if level_now > level_before:
                    await message.channel.send(f"{message.author.mention} just leveled up! (level **{level_now}**)")


def setup(client):
    client.add_cog(Events(client))
