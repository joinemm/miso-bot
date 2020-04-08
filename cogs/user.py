import discord
import arrow
import random
import re
import aiohttp
from lxml.html import clean
from discord.ext import commands
from operator import itemgetter
from libraries import plotter
from data import database as db
from helpers import utilityfunctions as util


ALLSUM = "SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23)"


class User(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        with open("html/profile.html", "r", encoding="utf-8") as file:
            self.profile_html = file.read()

    async def get_rank(self, ctx, user, table, _global=False):
        """Get user's xp ranking from given table."""
        if user.bot:
            return 'BOT'

        users = []
        if _global:
            rows = db.query(
                "SELECT user_id, %s FROM %s GROUP BY user_id ORDER BY %s DESC" % (ALLSUM, table, ALLSUM)
            )
        else:
            rows = db.query(
                "SELECT user_id, %s FROM %s WHERE guild_id = ? GROUP BY user_id ORDER BY %s DESC" % (ALLSUM, table, ALLSUM),
                (ctx.guild.id,)
            )

        total = 0
        i = 0
        ranking = 'N/A'
        for user_id, total_x in rows:
            this_user = self.bot.get_user(user_id)
            if this_user is None or this_user.bot:
                continue
            else:
                total += 1
                i += 1

            if user_id == user.id:
                ranking = i

        return f"#{ranking}/{total}"
        
    @commands.command(aliases=['dp'])
    async def avatar(self, ctx, *, user: discord.User=None):
        """Get user's profile picture."""
        if user is None:
            user = ctx.author

        content = discord.Embed()
        content.set_author(name=str(user), url=user.avatar_url)
        content.set_image(url=user.avatar_url_as(static_format='png'))
        stats = await util.image_info_from_url(user.avatar_url)
        color = await util.color_from_image_url(str(user.avatar_url_as(size=128, format='png')))
        content.color = await util.get_color(ctx, color)
        content.set_footer(text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}")

        await ctx.send(embed=content)

    @commands.command()
    async def userinfo(self, ctx, *, user=None):
        """Get information about user"""
        user = await util.get_member(ctx, user, ctx.author, try_user=True)
        if user is None:
            return await ctx.send(":warning: Could not find this user")

        fishydata = db.fishdata(user.id)
        if fishydata is None or fishydata.timestamp is None:
            fishy_time = "Never"
        else:
            fishy_time = arrow.get(fishydata.timestamp).humanize()

        status_emoji = {
            "online": "<:online:643451789106085888>",
            "idle": "<:away:643452166769737730>",
            "dnd": "<:dnd:643451849457926174>",
            "offline": "<:offline:643451886187315211>"
        }
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
        content.set_thumbnail(url=user.avatar_url)
        content.add_field(name="Status", value=status)
        content.add_field(name="Activity", value=activity)
        content.add_field(name="Fishy", value=f"{fishydata.fishy if fishydata is not None else 0}")
        content.add_field(name="Last fishy", value=fishy_time)
        content.add_field(name="Account created", value=user.created_at.strftime('%d/%m/%Y %H:%M'))

        # Skip info only available from the guild
        if isinstance(user, discord.Member):
            content.colour = user.color
            content.add_field(
                name="Joined server",
                value=user.joined_at.strftime('%d/%m/%Y %H:%M')
            )

            member_number = 1
            for member in ctx.guild.members:
                if member.joined_at < user.joined_at:
                    member_number += 1
            content.add_field(
                name="Member",
                value=f"#{member_number} / {len(ctx.guild.members)}"
            )

            roles_names = []
            for role in user.roles:
                roles_names.append(role.mention)

            role_string = " ".join(role.mention for role in user.roles)
            content.add_field(
                name="Roles",
                value=role_string,
                inline=False
            )

        await ctx.send(embed=content)

    @commands.command()
    async def hug(self, ctx, *, huggable=None):
        """hug someone or something."""
        emojis = db.query("select id from emojis where type = 'hug'")
        emoji = self.bot.get_emoji(random.choice(emojis)[0])

        if huggable is not None:
            parsed_words = []
            for word in huggable.split(" "):
                user = await util.get_user(ctx, word)
                parsed_words.append(user.mention if user is not None else word)

            text = " ".join(parsed_words)
            await ctx.send(f"{text} {emoji}")
        else:
            await ctx.send(f"{emoji}")

    @commands.command()
    async def members(self, ctx):
        """Show the newest members of this server."""
        sorted_members = sorted(ctx.guild.members, key=lambda x: x.joined_at, reverse=True)

        content = discord.Embed(title=f"{ctx.guild.name} members")
        rows = []
        for i, member in enumerate(sorted_members):
            jointime = member.joined_at.strftime('%y%m%d %H:%M')
            rows.append(
                f"[`{jointime}`] **#{len(sorted_members)-i}** : **{member.name}**"
            )

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def serverinfo(self, ctx):
        """Get information about this server."""
        image_small = str(ctx.guild.icon_url_as(format='png', size=64))
        content = discord.Embed(color=int(await util.color_from_image_url(image_small), 16))
        content.title = f"**{ctx.guild.name}** | #{ctx.guild.id}"
        content.add_field(name="Owner", value=f"{ctx.guild.owner.name}#{ctx.guild.owner.discriminator}")
        content.add_field(name="Region", value=str(ctx.guild.region))
        content.add_field(name="Created At", value=ctx.guild.created_at.strftime('%d/%m/%Y %H:%M'))
        content.add_field(name="Members", value=str(ctx.guild.member_count))
        content.add_field(name="Roles", value=str(len(ctx.guild.roles)))
        content.add_field(name="Emojis", value=str(len(ctx.guild.emojis)))
        content.add_field(
            name="Channels",
            value=f"{len(ctx.guild.text_channels)} Text channels, {len(ctx.guild.voice_channels)} Voice channels"
        )
        content.set_thumbnail(url=ctx.guild.icon_url)

        await ctx.send(embed=content)

    @commands.command()
    async def roleslist(self, ctx):
        """List the roles of this server."""
        content = discord.Embed(title=f"Roles in {ctx.message.guild.name}")
        rows = []
        for role in reversed(ctx.message.guild.roles):
            rows.append(
                f"[`{role.id} | {str(role.color)}`] **x{len(role.members)}**"
                f"{':warning:' if len(role.members) == 0 else ''}: {role.mention}"
            )

        await util.send_as_pages(ctx, content, rows)

    @commands.command(aliases=["level"])
    async def activity(self, ctx, user: discord.Member=None):
        """See your hourly server activity chart (GMT)"""
        if user is None:
            user = ctx.author

        activitydata = db.activitydata(ctx.guild.id, user.id)
        if activitydata is None:
            return await ctx.send(f"No activity for `{user}` found on this server")

        activities = list(activitydata[3:])
        xp = sum(activities)
        level = util.get_level(xp)

        title = f"LVL {level} | {xp - util.get_xp(level)}/" \
                f"{util.xp_to_next_level(level)} XP to levelup | Total xp: {xp}"

        await self.bot.loop.run_in_executor(
            None, lambda: plotter.create_graph(activities, str(user.color), title=title)
        )

        with open("downloads/graph.png", "rb") as img:
            await ctx.send(f"`Hourly cumulative server activity for {user}`", file=discord.File(img))

    @commands.command()
    async def rank(self, ctx, user: discord.Member=None):
        """See your xp ranking."""
        if user is None:
            user = ctx.author

        content = discord.Embed(color=user.color)
        content.set_author(
            name=f"XP Rankings for {user.name}",
            icon_url=user.avatar_url
        )
        
        for globalrank in [False, True]:
            textbox = "```"
            for table, label in zip(['activity_day', 'activity_week', 'activity_month', 'activity'],
                                    ["Daily  ", "Weekly ", "Monthly", "Overall"]):
                ranking = await self.get_rank(ctx, user, table, globalrank)
                textbox += f"\n{label} : {ranking}"
            
            content.add_field(name='Global' if globalrank else 'Server', value=textbox + '```')

        await ctx.send(embed=content)

    @commands.command()
    async def topservers(self, ctx):
        """See your top servers with miso bot."""
        data = db.query(
                "SELECT guild_id, %s FROM activity WHERE user_id = ? GROUP BY guild_id ORDER BY %s DESC" % (ALLSUM, ALLSUM),
                (ctx.author.id,)
            )
        rows = []
        total_xp = 0
        for i, (guild_id, xp) in enumerate(data, start=1):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                guild = guild_id
            else:
                guild = guild.name

            level = util.get_level(xp)
            total_xp += xp
            rows.append(f"`#{i}` **{guild}** — Level **{level}**")
        
        content = discord.Embed()
        content.set_author(name=f"{ctx.author.name}'s top servers", icon_url=ctx.author.avatar_url)
        content.set_footer(text=f"Global level {util.get_level(total_xp)}")
        content.color = ctx.author.color
        await util.send_as_pages(ctx, content, rows)

    @commands.group(case_insensitive=True)
    async def leaderboard(self, ctx):
        """Show various leaderboards."""
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
                user = self.bot.get_user(user_id)
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

        content = discord.Embed(
            title=f"{'global' if _global_ else ctx.guild.name} fishy leaderboard",
            color=discord.Color.blue()
        )
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name='fishysize')
    async def leaderboard_fishysize(self, ctx):
        data = db.query("SELECT * FROM fishysize ORDER BY size DESC")
        content = discord.Embed(title="Biggest fishies caught :fish:", color=discord.Color.blue())
        rows = []
        rank_icon = [':first_place:', ':second_place:', ':third_place:']
        for i, row in enumerate(data, start=1):
            fisher = self.bot.get_user(row[2] or '')
            receiver = self.bot.get_user(row[3])
            if fisher is None:
                fisher = receiver
                receiver = None

            if i <= len(rank_icon):
                rank = rank_icon[i - 1]
            else:
                rank = f"`{i}.`"

            rows.append(f"{rank} **{row[4]} Kg** caught by **{fisher}**"
                        + (f" for **{receiver}**" if receiver is not None else ""))

        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name='levels')
    async def leaderboard_levels(self, ctx, scope='', timeframe=''):
        _global_ = scope == 'global'
        if timeframe == '':
            timeframe = scope
        users = []
        guild = ctx.guild
        ALLSUM = "SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23)"

        time, table = get_activity_table(timeframe)
        if _global_:
            user_rows = db.query(
                "SELECT user_id, %s, SUM(messages) FROM %s GROUP BY user_id " 
                "ORDER BY %s DESC" % (ALLSUM, table, ALLSUM)
            )
            for user_id, xp, messages in user_rows:
                user = self.bot.get_user(user_id)
                if user is None or user.bot:
                    continue

                users.append((user, messages, xp))
        else:
            # guild selector for owner only
            if ctx.author.id == 133311691852218378 and scope != '':
                try:
                    guild = self.bot.get_guild(int(scope))
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
            rows.append(f"`#{i:2}` " + (f"LVL **{util.get_level(xp)}** - " if time is None else '') +
                        f"**{user.name}** `[{xp} XP | {messages} messages]`")

        content = discord.Embed(color=discord.Color.teal())
        content.title = f"{'Global' if _global_ else guild.name} levels leaderboard"
        if time is not None:
            content.title += f" - {time}"
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name='wpm')
    async def leaderboard_wpm(self, ctx, scope=''):
        _global_ = scope == 'global'
        userids = db.query("SELECT DISTINCT user_id FROM typingdata")
        if userids is None:
            return await ctx.send("No typing data exists yet!")

        users = []
        for userid in userids:
            userid = userid[0]
            data = db.query("SELECT MAX(wpm), `timestamp` FROM typingdata WHERE user_id = ?", (userid,))[0]
            wpm = data[0]
            timestamp = data[1]

            if _global_:
                user = self.bot.get_user(userid)
            else:
                user = ctx.guild.get_member(userid)
            if user is None:
                continue

            users.append((user, wpm, timestamp))

        if not users:
            return await ctx.send("No typing data exists yet on this server!")

        rows = []
        rank_icon = [':first_place:', ':second_place:', ':third_place:']
        for i, (user, wpm, timestamp) in enumerate(sorted(users, key=itemgetter(1), reverse=True), start=1):
            if i <= len(rank_icon):
                ranking = rank_icon[i - 1]
            else:
                ranking = f"`{i}.`"
            rows.append(f"{ranking} **{int(wpm)}** WPM — **{user.name}** ( {arrow.get(timestamp).humanize()} )")
        content = discord.Embed(title=":keyboard: WPM Leaderboard", color=discord.Color.orange())
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

            rows.append((f"`{rank}:`" if rank > 1 else ":crown:") + f" **{count}** crowns - **{user.name}**")
            rank += 1
        content = discord.Embed(color=discord.Color.gold())
        content.title = f"{ctx.guild.name} artist crowns leaderboard"
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def profile(self, ctx, user: discord.Member=None):
        """Your personal customizable user profile."""
        if user is None:
            user = ctx.author

        activity = str(db.get_user_activity(ctx.guild.id, user.id))
        fishydata = db.fishdata(user.id)

        local_xp_rows = db.query("SELECT * FROM activity WHERE user_id = ? AND guild_id = ?", (user.id, ctx.guild.id))
        local_xp = 0
        if local_xp_rows is not None:
            local_xp = sum(list(local_xp_rows[0][3:]))
            local_rank = await self.get_rank(ctx, user, 'activity')

        global_xp_rows = db.query("SELECT * FROM activity WHERE user_id = ?", (user.id,))
        global_xp = 0
        if global_xp_rows is not None:
            global_xp = sum(sum(row[3:]) for row in global_xp_rows)
            global_rank = await self.get_rank(ctx, user, 'activity', _global=True)
         
        patrons = db.query("select user_id from patrons where currently_active = 1")
        if user.id == self.bot.owner.id:
            corner_icon = 'fa-dev'
        elif patrons is not None and user.id in [x[0] for x in patrons]:
            corner_icon = 'fa-patreon'
        else:
            corner_icon = ''
            
        activity_formatted = util.activityhandler(user.activities)

        description = db.query("SELECT description FROM profiles WHERE user_id = ?", (user.id,))
        if description is None or description[0][0] is None:
            description = "<p>use >editprofile to change your description</p>"
        else:
            cleaner = clean.Cleaner(safe_attrs_only=True)
            description = cleaner.clean_html(description[0][0].replace('\n', '<br>'))

        background_url = db.query("SELECT background_url FROM profiles WHERE user_id = ?", (user.id,))
        if background_url is None:
            background_url = ''
        else:
            background_url = background_url[0][0]

        replacements = {
            'BACKGROUND_IMAGE': background_url,
            'ACCENT_COLOR': user.color,
            'AVATAR_URL': user.avatar_url_as(size=128, format='png'),
            'USERNAME': f"{user.name} #{user.discriminator}",
            'DESCRIPTION': description,
            'FISHY': fishydata.fishy if fishydata is not None else 0,
            'LVL_LOCAL': util.get_level(local_xp),
            'RANK_LOCAL': local_rank,
            'LVL_GLOBAL': util.get_level(global_xp),
            'RANK_GLOBAL': global_rank,
            'ACTIVITY_ICON': activity_formatted.get('icon'),
            'ACTIVITY_TEXT': activity_formatted.get('text'),
            'ACTIVITY_DATA': activity,
            'PATREON': corner_icon
        }

        def dictsub(m):
            return str(replacements[m.group().strip('%')])

        formatted_html = re.sub(r'%%(\S*)%%', dictsub, self.profile_html)
        
        async with aiohttp.ClientSession() as session:
            data = {
                'html': formatted_html,
                'width': 512, 
                'height': 512,
                'imageFormat': 'png'
            }
            async with session.post('http://localhost:3000/html', data=data) as response: 
                with open("downloads/profile.png", "wb") as f:
                    while True:
                        block = await response.content.read(1024)
                        if not block:
                            break
                        f.write(block)

        with open("downloads/profile.png", "rb") as f:
            await ctx.send(file=discord.File(f))
        
    @commands.group()
    async def editprofile(self, ctx):
        await util.command_group_help(ctx)

    @editprofile.command(name='description', rest_is_raw=True)
    async def editprofile_description(self, ctx, *, text):
        if text.strip() == '':
            return await util.send_command_help(ctx)
        db.execute("INSERT OR IGNORE INTO profiles VALUES (?, ?, ?, ?)", (ctx.author.id, None, None, None))
        db.execute("UPDATE profiles SET description = ? WHERE user_id = ?", (text[1:], ctx.author.id))
        await ctx.send("Description updated!")

    @editprofile.command(name='background')
    async def editprofile_background(self, ctx, url):
        patrons = db.query("select user_id from patrons where currently_active = 1")
        if ctx.author != self.bot.owner:
            if ctx.author.id not in [x[0] for x in patrons]:
                return await ctx.send("Sorry, only patreon supporters can use this feature!")
        db.execute("INSERT OR IGNORE INTO profiles VALUES (?, ?, ?, ?)", (ctx.author.id, None, None, None))
        db.execute("UPDATE profiles SET background_url = ? WHERE user_id = ?", (url, ctx.author.id))
        await ctx.send("Background image updated!")

def setup(bot):
    bot.add_cog(User(bot))


def get_activity_table(timeframe):
    if timeframe in ["day", "daily"]:
        return 'Today', 'activity_day'
    if timeframe in ["week", "weekly"]:
        return 'This week', 'activity_week'
    if timeframe in ["month", "monthly"]:
        return 'This month', 'activity_month'
    else:
        return None, 'activity'
