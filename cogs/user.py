import discord
import arrow
from discord.ext import commands
import helpers.utilityfunctions as util
from libraries import plotter
import data.database as db
import random


class User(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(aliases=['dp'])
    async def avatar(self, ctx, *, user=""):
        """Get user's profile picture"""
        user = await util.get_user(ctx, user, ctx.author)

        content = discord.Embed(color=user.color)
        image = user.avatar_url_as(static_format="png")
        content.set_author(name=user.name, url=image)
        content.set_image(url=image)

        await ctx.send(embed=content)

    @commands.command()
    async def userinfo(self, ctx, *, user=""):
        """Get information about user"""
        user = await util.get_user(ctx, user, ctx.author)

        fishydata = db.fishdata(user.id)
        if fishydata is None or fishydata.timestamp is None:
            fishy_time = "Never"
        else:
            fishy_time = arrow.get(fishydata.timestamp).humanize()

        status_emoji = {"online": "<:online:533466178711191590>", "idle": "<:idle:533466151729102852>",
                        "dnd": "<:dnd:533466208377241614>", "offline": "<:offline:533466238567972874>"}
        try:
            status = f"{status_emoji[str(user.status)]}{str(user.status).capitalize()}"
            if user.is_on_mobile():
                status += " :iphone:"
        except AttributeError:
            status = "Unavailable"

        try:
            activity = str(user.activities[0]) if user.activities else "None"
        except AttributeError:
            activity = "Unknown"
        content = discord.Embed()
        try:
            content.colour = user.color
            member_number = 1
            for member in ctx.guild.members:
                if member.joined_at < user.joined_at:
                    member_number += 1
        except AttributeError:
            pass
        content.title = f"{user.name}#{user.discriminator} | #{user.id}"
        content.add_field(name="Status", value=status)
        content.add_field(name="Activity", value=activity)
        content.add_field(name="Fishy", value=f"{fishydata.fishy if fishydata is not None else 0}")
        content.add_field(name="Last fishy", value=fishy_time)
        content.add_field(name="Account created", value=user.created_at.strftime('%d/%m/%Y %H:%M'))
        try:
            content.add_field(name="Joined server", value=user.joined_at.strftime('%d/%m/%Y %H:%M'))
        except AttributeError:
            pass
        content.add_field(name="Member", value=f"#{member_number}")
        try:
            roles_names = []
            for role in user.roles:
                roles_names.append(role.mention)
            role_string = " ".join([role.mention for role in user.roles])
            content.add_field(name="Roles", value=role_string, inline=False)
        except AttributeError:
            pass
        content.set_thumbnail(url=user.avatar_url)

        await ctx.send(embed=content)

    @commands.command()
    async def hug(self, ctx, *, text=""):
        """hug someone or something"""
        parsed_words = []
        for word in text.split(" "):
            user = await util.get_user(ctx, word)
            parsed_words.append(user.mention if user is not None else word)
        text = " ".join(parsed_words)
        emojis = db.query("select id from emojis where type = 'hug'")
        emoji = self.client.get_emoji(random.choice(emojis)[0])
        await ctx.send(f"{text} {emoji}")

    @commands.command()
    async def members(self, ctx):
        """Show the newest members of this server"""
        sorted_members = sorted(ctx.guild.members, key=lambda x: x.joined_at, reverse=True)

        content = discord.Embed(title=f"{ctx.guild.name} members")
        rows = []
        for i, member in enumerate(sorted_members):
            rows.append(f"[`{member.joined_at.strftime('%y%m%d %H:%M')}`] "
                        f"**#{len(sorted_members)-i}** : **{member.name}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def serverinfo(self, ctx):
        """Get information about this server"""
        image_small = str(ctx.guild.icon_url_as(format='png', size=128))
        content = discord.Embed(color=int(util.color_from_image_url(image_small), 16))
        content.title = f"**{ctx.guild.name}** | #{ctx.guild.id}"
        content.add_field(name="Owner", value=f"{ctx.guild.owner.name}#{ctx.guild.owner.discriminator}")
        content.add_field(name="Region", value=str(ctx.guild.region))
        content.add_field(name="Created At", value=ctx.guild.created_at.strftime('%d/%m/%Y %H:%M'))
        content.add_field(name="Members", value=str(ctx.guild.member_count))
        content.add_field(name="Roles", value=str(len(ctx.guild.roles)))
        content.add_field(name="Emojis", value=str(len(ctx.guild.emojis)))
        content.add_field(name="Channels", value=f"{len(ctx.guild.text_channels)} Text channels, "
                                                 f"{len(ctx.guild.voice_channels)} Voice channels")
        content.set_thumbnail(url=ctx.guild.icon_url)

        await ctx.send(embed=content)

    @commands.command()
    async def roleslist(self, ctx):
        """List the roles of this server"""
        content = discord.Embed(title=f"Roles in **{ctx.message.guild.name}**")
        rows = []
        for role in reversed(ctx.message.guild.roles):
            item = f"[`{role.id} | {str(role.color)}`] **x{len(role.members)}**" \
                   f"{'<' if len(role.members) == 0 else ' '}: {role.mention}"
            rows.append(item)

        await util.send_as_pages(ctx, content, rows)

    @commands.command(aliases=['levels'])
    async def toplevels(self, ctx, _global=None):
        """Levels leaderboard"""
        users = []
        guild = ctx.guild
        if _global == "global":
            user_ids = db.query("SELECT DISTINCT user_id FROM activity")
            for user_id in [x[0] for x in user_ids]:
                rows = db.query("SELECT * FROM activity WHERE user_id = ?", (user_id, ))
                user = self.client.get_user(user_id)
                if user is None:
                    continue
                users.append((user, sum(row[2] for row in rows), sum(sum(row[3:]) for row in rows)))
        else:
            if ctx.author.id == 133311691852218378:
                try:
                    guild = self.client.get_guild(int(_global))
                    if guild is None:
                        guild = ctx.guild
                except TypeError:
                    pass
            data = db.query("SELECT * FROM activity WHERE guild_id = ?", (guild.id,))
            for row in data:
                user = guild.get_member(row[1])
                if user is None:
                    continue
                users.append((user, row[2], sum(row[3:])))

        rows = []
        for i, (user, messages, xp) in enumerate(sorted(users, key=lambda tup: tup[2], reverse=True), start=1):
            rows.append(f"`{i}:` LVL **{util.get_level(xp)}** - **{user.name}** `[{xp} XP | {messages} messages]`")

        content = discord.Embed(color=discord.Color.green(),
                                title=f"{'Global l' if _global == 'global' else 'L'}evels leaderboard"
                                f"{'' if _global == 'global' else f' for {guild.name}'}")
        await util.send_as_pages(ctx, content, rows)

    @commands.command(aliases=["level"])
    async def activity(self, ctx, user=""):
        """See your hourly server activity chart"""
        user = await util.get_user(ctx, user, ctx.author)

        activitydata = db.activitydata(ctx.guild.id, user.id)
        if activitydata is None:
            return await ctx.send(f"No activity for `{user}` found on this server")

        activities = list(activitydata[3:])
        xp = sum(activities)
        level = util.get_level(xp)

        title = f"LVL {level} | {xp - util.get_xp(level)}/" \
                f"{util.xp_to_next_level(level)} XP to levelup | Total xp: {xp}"

        plotter.create_graph(activities, str(user.color), title=title)

        with open("downloads/graph.png", "rb") as img:
            await ctx.send(file=discord.File(img))


def setup(client):
    client.add_cog(User(client))
