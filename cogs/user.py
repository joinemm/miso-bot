import discord
import arrow
import re
import aiohttp
import bleach
import typing
from discord.ext import commands
from operator import itemgetter
from libraries import plotter
from data import database as db
from helpers import utilityfunctions as util
from helpers import emojis

ALLSUM = (
    "SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23)"
)


class User(commands.Cog):
    """User related commands"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "👤"
        with open("html/new_profile.html", "r", encoding="utf-8") as file:
            self.profile_html = file.read()

    async def get_rank(self, ctx, user, table="activity", _global=False):
        """Get user's xp ranking from given table."""
        if user.bot:
            return "BOT"

        if _global:
            rows = db.query(
                "SELECT user_id, %s FROM %s GROUP BY user_id ORDER BY %s DESC"
                % (ALLSUM, table, ALLSUM)
            )
        else:
            rows = db.query(
                "SELECT user_id, %s FROM %s WHERE guild_id = ? GROUP BY user_id ORDER BY %s DESC"
                % (ALLSUM, table, ALLSUM),
                (ctx.guild.id,),
            )

        total = 0
        i = 0
        ranking = "N/A"
        for user_id, total_x in rows:
            if _global:
                this_user = self.bot.get_user(user_id)
            else:
                this_user = ctx.guild.get_member(user_id)
            if this_user is None or this_user.bot:
                continue
            else:
                total += 1
                i += 1

            if user_id == user.id:
                ranking = i

        return f"#{ranking} / {total}"

    @commands.command(aliases=["dp", "av", "pfp"])
    async def avatar(self, ctx, *, user: discord.User = None):
        """Get user's profile picture."""
        if user is None:
            user = ctx.author

        content = discord.Embed()
        content.set_author(name=str(user), url=user.avatar_url)
        content.set_image(url=user.avatar_url_as(static_format="png"))
        stats = await util.image_info_from_url(user.avatar_url)
        color = await util.color_from_image_url(str(user.avatar_url_as(size=128, format="png")))
        content.colour = await util.get_color(ctx, color)
        if stats is not None:
            content.set_footer(
                text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
            )

        await ctx.send(embed=content)

    @commands.command(aliases=["uinfo"])
    @commands.cooldown(3, 30, type=commands.BucketType.user)
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

        try:
            state = str(user.status)
            status = emojis.Status[state.upper()].value + state.capitalize()
            if user.is_on_mobile():
                status += " :iphone:"
        except AttributeError:
            status = "Unavailable"

        content = discord.Embed()
        content.title = f"{user.name}#{user.discriminator} | #{user.id}"
        content.set_thumbnail(url=user.avatar_url)
        content.add_field(name="Status", value=status)

        if isinstance(user, discord.Member):
            activity = util.activities_string(user.activities)
            content.add_field(name="Activity", value=activity)

        content.add_field(name="Fishy", value=f"{fishydata.fishy if fishydata is not None else 0}")
        content.add_field(name="Last fishy", value=fishy_time)
        content.add_field(name="Account created", value=user.created_at.strftime("%d/%m/%Y %H:%M"))

        # Skip info only available from the guild
        if isinstance(user, discord.Member):
            content.colour = user.color
            content.add_field(
                name="Joined server", value=user.joined_at.strftime("%d/%m/%Y %H:%M")
            )

            member_number = 1
            for member in ctx.guild.members:
                if member.joined_at < user.joined_at:
                    member_number += 1
            content.add_field(name="Member", value=f"#{member_number} / {len(ctx.guild.members)}")
            content.add_field(name="Server rank", value=await self.get_rank(ctx, user))
            # content.add_field(
            #    name="Global Rank", value=await self.get_rank(ctx, user, _global=True)
            # )

            role_string = (
                " ".join(role.mention for role in reversed(user.roles[1:]))
                if len(user.roles) > 1
                else "None"
            )
            content.add_field(name="Roles", value=role_string, inline=False)

        await ctx.send(embed=content)

    @commands.command()
    async def hug(self, ctx, *, huggable=None):
        """hug someone or something."""
        emoji = emojis.random_hug()

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
        membercount = len(sorted_members)
        content = discord.Embed(title=f"{ctx.guild.name} members")
        rows = []
        for i, member in enumerate(sorted_members):
            jointime = member.joined_at.strftime("%y%m%d %H:%M")
            rows.append(f"[`{jointime}`] **#{membercount-i}** : **{member}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command(aliases=["sinfo"])
    async def serverinfo(self, ctx):
        """Get information about this server."""
        image_small = str(ctx.guild.icon_url_as(format="png", size=64))
        content = discord.Embed(color=int(await util.color_from_image_url(image_small), 16))
        content.title = f"**{ctx.guild.name}** | #{ctx.guild.id}"
        content.add_field(name="Owner", value=str(ctx.guild.owner))
        content.add_field(name="Region", value=str(ctx.guild.region))
        content.add_field(name="Created At", value=ctx.guild.created_at.strftime("%d/%m/%Y %H:%M"))
        content.add_field(name="Members", value=str(ctx.guild.member_count))
        content.add_field(name="Roles", value=str(len(ctx.guild.roles)))
        content.add_field(name="Emojis", value=str(len(ctx.guild.emojis)))
        content.add_field(
            name="Channels",
            value=f"{len(ctx.guild.text_channels)} Text channels, "
            f"{len(ctx.guild.voice_channels)} Voice channels",
        )
        content.set_thumbnail(url=ctx.guild.icon_url)

        await ctx.send(embed=content)

    @commands.command(aliases=["roles"])
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
    async def activity(self, ctx, user: typing.Optional[discord.Member] = None, scope=""):
        """See your hourly activity chart (GMT)."""
        if user is None:
            user = ctx.author

        is_global = scope.lower() == "global"

        if is_global:
            activitydata = db.global_activitydata(user.id)
        else:
            activitydata = db.get_user_activity(ctx.guild.id, user.id)

        if activitydata is None:
            return await ctx.send("No activity found!")

        activities = list(activitydata)
        xp = sum(activities)
        level = util.get_level(xp)

        title = (
            f"LVL {level} | {xp - util.get_xp(level)}/"
            f"{util.xp_to_next_level(level)} XP to levelup | Total xp: {xp}"
        )

        await self.bot.loop.run_in_executor(
            None, lambda: plotter.create_graph(activities, str(user.color), title=title)
        )

        with open("downloads/graph.png", "rb") as img:
            await ctx.send(
                f"`Hourly cumulative {'global' if is_global else 'server'} activity for {user}`",
                file=discord.File(img),
            )

    @commands.command(aliases=["ranking"])
    @commands.cooldown(3, 30, type=commands.BucketType.user)
    async def rank(self, ctx, user: discord.Member = None):
        """See your xp ranking."""
        if user is None:
            user = ctx.author

        content = discord.Embed(color=user.color)
        content.set_author(name=f"XP Rankings for {user.name}", icon_url=user.avatar_url)

        for globalrank in [False, True]:
            textbox = "```"
            for table, label in zip(
                ["activity_day", "activity_week", "activity_month", "activity"],
                ["Daily  ", "Weekly ", "Monthly", "Overall"],
            ):
                ranking = await self.get_rank(ctx, user, table, globalrank)
                textbox += f"\n{label} : {ranking}"

            content.add_field(name="Global" if globalrank else "Server", value=textbox + "```")

        await ctx.send(embed=content)

    @commands.command()
    async def topservers(self, ctx, user: discord.User = None):
        """See your top servers with miso bot."""
        if user is None:
            user = ctx.author

        data = db.query(
            """SELECT guild_id, %s FROM activity
            WHERE user_id = ? GROUP BY guild_id ORDER BY %s DESC"""
            % (ALLSUM, ALLSUM),
            (user.id,),
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
        content.set_author(name=f"{user.name}'s top servers", icon_url=ctx.author.avatar_url)
        content.set_footer(text=f"Global level {util.get_level(total_xp)}")
        content.colour = ctx.author.color
        await util.send_as_pages(ctx, content, rows)

    @commands.group(case_insensitive=True, aliases=["lb"])
    async def leaderboard(self, ctx):
        """Show various leaderboards."""
        await util.command_group_help(ctx)

    @leaderboard.command(name="fishy")
    async def leaderboard_fishy(self, ctx, scope=""):
        _global_ = scope == "global"
        users = db.query("select user_id, fishy from fishy order by fishy desc")
        rows = []
        rank_icon = [":first_place:", ":second_place:", ":third_place:"]
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

            rows.append(f"{ranking} {util.displayname(user)} - **{fishy}** fishy")
            rank += 1

        if not rows:
            return await ctx.send("Nobody has been fishing yet on this server!")

        content = discord.Embed(
            title=f"{'global' if _global_ else ctx.guild.name} fishy leaderboard",
            color=discord.Color.blue(),
        )
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="levels", aliases=["xp", "level"])
    async def leaderboard_levels(self, ctx, scope="", timeframe=""):
        _global_ = scope == "global"
        if timeframe == "":
            timeframe = scope
        users = []
        guild = ctx.guild

        time, table = get_activity_table(timeframe)
        if _global_:
            user_rows = db.query(
                "SELECT user_id, %s, SUM(messages) FROM %s GROUP BY user_id "
                "ORDER BY %s DESC" % (ALLSUM, table, ALLSUM)
            )
            for user_id, xp, messages in user_rows:
                if _global_:
                    user = self.bot.get_user(user_id)
                else:
                    user = ctx.guild.get_member(user_id)

                if user is None or user.bot:
                    continue

                users.append((user, messages, xp))
        else:
            # guild selector for owner only
            if ctx.author.id == self.bot.owner_id and scope != "":
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
        for i, (user, messages, xp) in enumerate(
            sorted(users, key=itemgetter(2), reverse=True), start=1
        ):
            rows.append(
                f"`#{i:2}` "
                + (f"LVL **{util.get_level(xp)}** - " if time is None else "")
                + f"**{util.displayname(user)}** `[{xp} XP | {messages} messages]`"
            )

        content = discord.Embed(color=discord.Color.teal())
        content.title = f"{'Global' if _global_ else guild.name} levels leaderboard"
        if time is not None:
            content.title += f" - {time}"
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="wpm", aliases=["typing"])
    async def leaderboard_wpm(self, ctx, scope=""):
        _global_ = scope == "global"

        data = db.query(
            """
            SELECT user_id, MAX(wpm), timestamp FROM typingdata
            GROUP BY user_id ORDER BY wpm desc
            """
        )

        rank_icon = [":first_place:", ":second_place:", ":third_place:"]
        rows = []
        i = 1
        for userid, wpm, timestamp in data:
            if _global_:
                user = self.bot.get_user(userid)
            else:
                user = ctx.guild.get_member(userid)

            if user is None:
                continue

            if i <= len(rank_icon):
                ranking = rank_icon[i - 1]
            else:
                ranking = f"`{i}.`"

            rows.append(
                f"{ranking} **{int(wpm)}** WPM — **{util.displayname(user)}** ( {arrow.get(timestamp).humanize()} )"
            )
            i += 1

        if not rows:
            return await ctx.send("No typing data exists yet on this server!")

        content = discord.Embed(title=":keyboard: WPM Leaderboard", color=discord.Color.orange())
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="crowns")
    async def leaderboard_crowns(self, ctx):
        data = db.query(
            "SELECT user_id, COUNT(1) FROM crowns WHERE guild_id = ? GROUP BY user_id",
            (ctx.guild.id,),
        )
        if data is None:
            return await ctx.send(
                "No crown data for this server exists yet! "
                "Use the `>whoknows` command to gain crowns"
            )
        rows = []
        rank = 1
        for user_id, count in sorted(data, key=itemgetter(1), reverse=True):
            user = ctx.guild.get_member(user_id)
            if user is None:
                continue

            rows.append(
                (f"`{rank}:`" if rank > 1 else ":crown:")
                + f" **{count}** crowns - **{util.displayname(user)}**"
            )
            rank += 1
        content = discord.Embed(color=discord.Color.gold())
        content.title = f"{ctx.guild.name} artist crowns leaderboard"
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def profile(self, ctx, user: discord.Member = None):
        """Your personal customizable user profile."""
        if user is None:
            user = ctx.author

        badges = []
        badge_classes = {
            "dev": "fab fa-dev",
            "patreon": "fab fa-patreon",
            "lastfm": "fab fa-lastfm",
            "sunsign": "fas fa-sun",
            "location": "fas fa-compass",
            "bot": "fas fa-robot",
        }

        def get_font_size(username):
            length = len(username)
            if length < 15:
                return "24px"
            elif length < 20:
                return "18px"
            elif length < 25:
                return "15px"
            else:
                return "11px"

        def make_badge(classname):
            return f'<li class="badge-container"><i class="corner-logo {classname}"></i></li>'

        # activity = db.get_user_activity(ctx.guild.id, user.id)
        activity = db.global_activitydata(user.id)
        fishydata = db.fishdata(user.id)

        local_xp_rows = db.query(
            "SELECT * FROM activity WHERE user_id = ? AND guild_id = ?",
            (user.id, ctx.guild.id),
        )
        local_xp = 0
        if local_xp_rows is not None:
            local_xp = sum(list(local_xp_rows[0][3:]))

        global_xp_rows = db.query("SELECT * FROM activity WHERE user_id = ?", (user.id,))
        global_xp = 0
        if global_xp_rows is not None:
            global_xp = sum(sum(row[3:]) for row in global_xp_rows)

        if user.id == self.bot.owner_id:
            badges.append(make_badge(badge_classes["dev"]))

        if user.bot:
            badges.append(make_badge(badge_classes["bot"]))

        patrons = db.query("select user_id from patrons where currently_active = 1")
        if patrons is not None and user.id in [x[0] for x in patrons]:
            badges.append(make_badge(badge_classes["patreon"]))

        description = db.query("SELECT description FROM profiles WHERE user_id = ?", (user.id,))
        if description is None or description[0][0] is None:
            if user.bot:
                description = "I am a bot<br>BEEP BOOP"
            else:
                description = "You should change this by using<br>>editprofile description"
        else:
            description = bleach.clean(
                description[0][0].replace("\n", "<br>"),
                tags=bleach.sanitizer.ALLOWED_TAGS + ["br"],
            )

        background_url = db.query(
            "SELECT background_url FROM profiles WHERE user_id = ?", (user.id,)
        )
        custom_bg = background_url is not None and str(background_url[0][0]).lower() != "none"

        command_count = 0
        command_uses = db.query(
            """
            SELECT SUM(count) FROM command_usage WHERE user_id = ? GROUP BY user_id
            """,
            (user.id,),
        )
        if command_uses is not None:
            command_count = command_uses[0][0]

        replacements = {
            "BACKGROUND_IMAGE": background_url[0][0] if custom_bg else "",
            "WRAPPER_CLASS": "custom-bg" if custom_bg else "",
            "SIDEBAR_CLASS": "blur" if custom_bg else "",
            "OVERLAY_CLASS": "overlay" if custom_bg else "",
            "USER_COLOR": user.color,
            "AVATAR_URL": user.avatar_url_as(size=128, format="png"),
            "USERNAME": user.name,
            "DISCRIMINATOR": f"#{user.discriminator}",
            "DESCRIPTION": description,
            "FISHY_AMOUNT": fishydata.fishy if fishydata is not None else 0,
            "SERVER_LEVEL": util.get_level(local_xp),
            "GLOBAL_LEVEL": util.get_level(global_xp),
            "ACTIVITY_DATA": str(activity),
            "CHART_MAX": max(activity),
            "COMMANDS_USED": command_count,
            "BADGES": "\n".join(badges),
            "USERNAME_SIZE": get_font_size(user.name),
        }

        def dictsub(m):
            return str(replacements[m.group().strip("%")])

        formatted_html = re.sub(r"%%(\S*)%%", dictsub, self.profile_html)

        async with aiohttp.ClientSession() as session:
            data = {
                "html": formatted_html,
                "width": 600,
                "height": 400,
                "imageFormat": "png",
            }
            async with session.post("http://localhost:3000/html", data=data) as response:
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

    @editprofile.command(name="description", rest_is_raw=True)
    async def editprofile_description(self, ctx, *, text):
        if text.strip() == "":
            return await util.send_command_help(ctx)

        db.execute(
            "INSERT OR IGNORE INTO profiles VALUES (?, ?, ?, ?)",
            (ctx.author.id, None, None, None),
        )
        db.execute(
            "UPDATE profiles SET description = ? WHERE user_id = ?",
            (text[1:], ctx.author.id),
        )
        await ctx.send(":white_check_mark: Profile description updated!")

    @util.patrons_only()
    @editprofile.command(name="background")
    async def editprofile_background(self, ctx, url):
        db.execute(
            "INSERT OR IGNORE INTO profiles VALUES (?, ?, ?, ?)",
            (ctx.author.id, None, None, None),
        )
        db.execute(
            "UPDATE profiles SET background_url = ? WHERE user_id = ?",
            (url, ctx.author.id),
        )
        await ctx.send(":white_check_mark: Background image updated!")


def setup(bot):
    bot.add_cog(User(bot))


def get_activity_table(timeframe):
    if timeframe in ["day", "daily"]:
        return "Today", "activity_day"
    if timeframe in ["week", "weekly"]:
        return "This week", "activity_week"
    if timeframe in ["month", "monthly"]:
        return "This month", "activity_month"
    else:
        return None, "activity"
