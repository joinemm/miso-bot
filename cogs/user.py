import discord
import arrow
from discord.ext import commands
import helpers.utilityfunctions as util
from libraries import plotter
import data.database as db
import random
from operator import itemgetter


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

        content.title = f"{user.name}#{user.discriminator} | #{user.id}"
        content.add_field(name="Status", value=status)
        content.add_field(name="Activity", value=activity)
        content.add_field(name="Fishy", value=f"{fishydata.fishy if fishydata is not None else 0}")
        content.add_field(name="Last fishy", value=fishy_time)
        content.add_field(name="Account created", value=user.created_at.strftime('%d/%m/%Y %H:%M'))

        # Skip info only available from the guild that the user is in if necessary
        try:
            content.colour = user.color
            content.add_field(name="Joined server", value=user.joined_at.strftime('%d/%m/%Y %H:%M'))
            member_number = 1
            for member in ctx.guild.members:
                if member.joined_at < user.joined_at:
                    member_number += 1
            content.add_field(name="Member", value=f"#{member_number}")

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

    @commands.command(aliases=['levels'], hidden=True)
    async def toplevels(self, ctx):
        await ctx.send(f"This command has been deprecated. Please use `>leaderboard levels [timeframe]`")

    @commands.command(aliases=["level"])
    async def activity(self, ctx, user=""):
        """See your hourly server activity chart (GMT)"""
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

    @commands.command()
    async def rank(self, ctx, user=""):
        user = await util.get_user(ctx, user, ctx.author)

        content = discord.Embed(color=user.color)
        content.set_author(name=f"XP Rankings for {user.name}", icon_url=user.avatar_url)
        content.description = "```"
        for table, label in zip(['activity_day', 'activity_week', 'activity_month', 'activity'],
                                ["Daily  ", "Weekly ", "Monthly", "Overall"]):
            users = []
            data = db.query("SELECT * FROM %s WHERE guild_id = ?" % table, (ctx.guild.id,))
            for row in data:
                this_user = ctx.guild.get_member(row[1])
                if this_user is None or this_user.bot:
                    continue
                users.append((row[1], sum(row[3:])))

            ranking = "N/A"
            for i, (userid, xp) in enumerate(sorted(users, key=itemgetter(1), reverse=True), start=1):
                if userid == user.id:
                    ranking = f"#{i}"

            content.description += f"\n{label} : {ranking}"

        content.description += "```"
        await ctx.send(embed=content)

    @commands.group()
    async def leaderboard(self, ctx):
        """Show various leaderboards"""
        await util.command_group_help(ctx)

    @leaderboard.command(name='fishy')
    async def leaderboard_fishy(self, ctx, scope=''):
        _global_ = scope == 'global'
        users = db.query("select user_id, fishy from fishy order by fishy desc")
        rows = []
        rank_icon = [':first_place:', ':second_place:', ':third_place:']
        rank = 1
        for user_id, fishy in users:
            if _global_:
                user = self.client.get_user(user_id)
            else:
                user = ctx.guild.get_member(user_id)
            if user is None:
                continue

            if fishy == 0:
                continue

            if rank <= len(rank_icon):
                ranking = rank_icon[rank - 1]
            else:
                ranking = f"`{rank}.`"

            rows.append(f"{ranking} {user.name} - **{fishy}** fishy")
            rank += 1

        if not rows:
            return await ctx.send("Nobody has been fishing yet on this server!")

        content = discord.Embed(title=f"{'global' if _global_ else ctx.guild.name} fishy leaderboard",
                                color=discord.Color.blue())

        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name='levels')
    async def leaderboard_levels(self, ctx, scope='', timeframe=''):
        _global_ = scope == 'global'
        if timeframe == '':
            timeframe = scope
        users = []
        guild = ctx.guild

        if _global_:
            time, table = get_activity_table(timeframe)
            user_ids = db.query("SELECT DISTINCT user_id FROM %s" % table)
            for user_id in [x[0] for x in user_ids]:
                rows = db.query("SELECT * FROM %s WHERE user_id = ?" % table, (user_id,))
                user = self.client.get_user(user_id)
                if user is None or user.bot:
                    continue

                users.append((user, sum(row[2] for row in rows), sum(sum(row[3:]) for row in rows)))
        else:
            time, table = get_activity_table(timeframe)
            # guild selector for owner only
            if ctx.author.id == 133311691852218378 and scope != '':
                try:
                    guild = self.client.get_guild(int(scope))
                    if guild is None:
                        guild = ctx.guild
                except ValueError:
                    pass

            data = db.query("SELECT * FROM %s WHERE guild_id = ?" % table, (guild.id,))
            for row in data:
                user = guild.get_member(row[1])
                if user is None or user.bot:
                    continue

                users.append((user, row[2], sum(row[3:])))

        rows = []
        for i, (user, messages, xp) in enumerate(sorted(users, key=itemgetter(2), reverse=True), start=1):
            rows.append(f"`{i}:` LVL **{util.get_level(xp)}** - **{user.name}** `[{xp} XP | {messages} messages]`")

        content = discord.Embed(color=discord.Color.teal())
        content.title = f"{'Global' if _global_ else guild.name} levels leaderboard"
        if time != '':
            content.title += f" - {time}"
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name='crowns')
    async def leaderboard_crowns(self, ctx):
        data = db.query("SELECT user_id, COUNT(1) FROM crowns WHERE guild_id = ? GROUP BY user_id",
                        (ctx.guild.id,))
        if data is None:
            return await ctx.send("No crown data for this server exists yet! "
                                  "Use the `>whoknows` command to gain crowns")
        rows = []
        rank = 1
        for user_id, count in sorted(data, key=itemgetter(1), reverse=True):
            user = ctx.guild.get_member(user_id)
            if user is None:
                continue

            rows.append(f"`{rank}:`" if rank > 1 else ":crown:" + f"**{count}** crowns - **{user.name}**")
            rank += 1
        content = discord.Embed(color=discord.Color.gold())
        content.title = f"{ctx.guild.name} artist crowns leaderboard"
        await util.send_as_pages(ctx, content, rows)


def setup(client):
    client.add_cog(User(client))


def get_activity_table(timeframe):
    if timeframe in ["day", "daily"]:
        return 'Today', 'activity_day'
    if timeframe in ["week", "weekly"]:
        return 'This week', 'activity_week'
    if timeframe in ["month", "monthly"]:
        return 'This month', 'activity_month'
    else:
        return '', 'activity'
