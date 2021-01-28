import discord
import bleach
import humanize
import typing
import arrow
from discord.ext import commands
from libraries import plotter
from modules import queries, emojis, exceptions, util


class User(commands.Cog):
    """User related commands"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "👤"
        self.medal_emoji = [":first_place:", ":second_place:", ":third_place:"]
        with open("html/profile.min.html", "r", encoding="utf-8") as file:
            self.profile_html = file.read()

    async def get_rank(self, user, table="user_activity", guild=None):
        """Get user's xp ranking from given table."""
        if guild is None:
            total, pos = (
                await self.bot.db.execute(
                    f"""
                    SELECT (SELECT COUNT(DISTINCT(user_id)) FROM {table} WHERE not is_bot),
                    ranking FROM (
                        SELECT RANK() OVER(ORDER BY xp DESC) AS ranking, user_id,
                            SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23) as xp
                        FROM {table}
                        WHERE not is_bot
                        GROUP BY user_id
                    ) as sub
                    WHERE user_id = %s
                    """,
                    user.id,
                    one_row=True,
                )
                or (None, None)
            )

        else:
            total, pos = (
                await self.bot.db.execute(
                    f"""
                    SELECT (SELECT COUNT(user_id) FROM {table} WHERE not is_bot AND guild_id = %s),
                    ranking FROM (
                        SELECT RANK() OVER(ORDER BY xp DESC) AS ranking, user_id,
                            SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23) as xp
                        FROM {table}
                        WHERE not is_bot
                        AND guild_id = %s
                        GROUP BY user_id
                    ) as sub
                    WHERE user_id = %s
                    """,
                    guild.id,
                    guild.id,
                    user.id,
                    one_row=True,
                )
                or (None, None)
            )

        if pos is None or total is None:
            return "N/A"
        else:
            return f"#{int(pos)} / {total}"

    @commands.command(aliases=["dp", "av", "pfp"])
    async def avatar(self, ctx, *, user: discord.User = None):
        """Get user's profile picture."""
        if user is None:
            user = ctx.author

        content = discord.Embed()
        content.set_author(name=str(user), url=user.avatar_url)
        content.set_image(url=user.avatar_url_as(static_format="png"))
        stats = await util.image_info_from_url(user.avatar_url)
        color = await util.color_from_image_url(str(user.avatar_url_as(size=64, format="png")))
        content.colour = await util.get_color(ctx, color)
        if stats is not None:
            content.set_footer(
                text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
            )

        await ctx.send(embed=content)

    @commands.command(aliases=["uinfo"])
    @commands.cooldown(3, 30, type=commands.BucketType.user)
    async def userinfo(self, ctx, *, user: discord.User = None):
        """Get information about discord user."""
        if user is None:
            user = ctx.author
        else:
            user = ctx.guild.get_member(user.id) or user

        content = discord.Embed(
            title=f"{user.name}#{user.discriminator}{' :robot:' if user.bot else ''} | #{user.id}"
        )
        content.set_thumbnail(url=user.avatar_url)

        if isinstance(user, discord.Member):
            content.color = user.color
            activity_display = util.activities_string(user.activities)
            if user.is_on_mobile() and user.status is discord.Status.online:
                status_emoji = "mobile"
            else:
                status_emoji = user.status.name
            status_display = f"{emojis.Status[status_emoji].value} {user.status.name.capitalize()}"

        else:
            activity_display = "Unavailable"
            status_display = "Unavailable"
            content.color = int(
                await util.color_from_image_url(str(user.avatar_url_as(size=64, format="png"))), 16
            )

        fishdata = await self.bot.db.execute(
            """
            SELECT fishy_count, last_fishy FROM fishy WHERE user_id = %s
            """,
            user.id,
            one_row=True,
        )
        if fishdata:
            fishy = fishdata[0]
            last_fishy = humanize.naturaltime(fishdata[1])
        else:
            fishy = 0
            last_fishy = "Never"

        content.add_field(name="Status", value=status_display)
        content.add_field(name="Activity", value=activity_display)
        content.add_field(name="Fishy", value=fishy)
        content.add_field(name="Last fishy", value=last_fishy)
        content.add_field(name="Account created", value=user.created_at.strftime("%d/%m/%Y %H:%M"))

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
            content.add_field(
                name="Server rank", value=await self.get_rank(user, "user_activity", user.guild)
            )
            content.add_field(name="Global Rank", value=await self.get_rank(user, "user_activity"))

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
            for word in huggable.split():
                user = await util.get_member(ctx, word)
                if user is not None:
                    huggable = huggable.replace(word, user.mention)

            await ctx.send(f"{huggable} {emoji}")
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

    @commands.command(aliases=["sinfo", "guildinfo"])
    async def serverinfo(self, ctx, guild_id: int = None):
        """Get information about discord server."""
        if guild_id is None:
            guild = ctx.guild
        else:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                raise exceptions.Warning(f'Guild with id "{guild_id}" not found.')

        image_small = str(guild.icon_url_as(format="png", size=64))
        content = discord.Embed(
            title=f"**{guild.name}** | #{guild.id}",
            color=int(await util.color_from_image_url(image_small), 16),
        )
        content.set_thumbnail(url=guild.icon_url)
        content.add_field(name="Owner", value=str(guild.owner))
        content.add_field(name="Region", value=f"{util.region_flag(guild.region)} {guild.region}")
        content.add_field(name="Created at", value=guild.created_at.strftime("%d/%m/%Y %H:%M"))
        content.add_field(name="Members", value=str(guild.member_count))
        content.add_field(name="Roles", value=str(len(guild.roles)))
        content.add_field(name="Emojis", value=str(len(guild.emojis)))
        content.add_field(name="Boost level", value=guild.premium_tier)
        content.add_field(name="Boosts", value=guild.premium_subscription_count)
        content.add_field(name="Filesize limit", value=humanize.naturalsize(guild.filesize_limit))
        content.add_field(
            name="Channels",
            value=(
                f"{len(guild.text_channels)} Text channels, "
                f"{len(guild.voice_channels)} Voice channels"
            ),
            inline=False,
        )

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
            global_activity = await self.bot.db.execute(
                """
                SELECT h0,h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,20,h21,h22,h23
                    FROM user_activity
                WHERE user_id = %s
                GROUP BY guild_id
                """,
                user.id,
            )
            if global_activity:
                activity_data = []
                for i in range(24):
                    activity_data.append(sum(r[i] for r in global_activity))
                xp = sum(activity_data)
            else:
                activity_data = [0] * 24
                xp = 0
        else:
            activity_data = await self.bot.db.execute(
                """
                SELECT h0,h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,20,h21,h22,h23
                    FROM user_activity
                WHERE user_id = %s AND guild_id = %s
                """,
                user.id,
                ctx.guild.id,
                one_row=True,
            )
            xp = sum(activity_data) if activity_data else 0

        if xp == 0:
            return ctx.send("No data!")

        level = util.get_level(xp)

        title = (
            f"LVL {level} | {xp - util.get_xp(level)}/"
            f"{util.xp_to_next_level(level)} XP to levelup | Total xp: {xp}"
        )

        await self.bot.loop.run_in_executor(
            None, lambda: plotter.create_graph(activity_data, str(user.color), title=title)
        )

        with open("downloads/graph.png", "rb") as img:
            await ctx.send(
                f"`Hourly cumulative {'global' if is_global else 'server'} activity for {user}`",
                file=discord.File(img),
            )

    @commands.command(aliases=["ranking"])
    @commands.cooldown(3, 30, type=commands.BucketType.user)
    async def rank(self, ctx, user: discord.Member = None):
        """See your XP ranking."""
        if user is None:
            user = ctx.author

        content = discord.Embed(color=user.color)
        content.set_author(
            name=f"XP Rankings for {util.displayname(user, escape=False)}",
            icon_url=user.avatar_url,
        )

        for guild in [ctx.guild, None]:
            textbox = "```"
            for table, label in [
                ("user_activity_day", "Daily  "),
                ("user_activity_week", "Weekly "),
                ("user_activity_month", "Monthly"),
                # (user_activity_year","Yearly "),
                ("user_activity", "Overall"),
            ]:
                ranking = await self.get_rank(user, table, guild)
                textbox += f"\n{label} : {ranking}"

            content.add_field(name="Global" if guild is None else "Server", value=textbox + "```")

        await ctx.send(embed=content)

    @commands.command()
    async def topservers(self, ctx):
        """See your top servers by XP."""
        data = await self.bot.db.execute(
            """
            SELECT guild_id, SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23)
                as xp FROM user_activity
                WHERE user_id = %s
            GROUP BY guild_id
            ORDER BY xp DESC
            """,
            ctx.author.id,
        )
        rows = []
        total_xp = 0
        for i, (guild_id, xp) in enumerate(data, start=1):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                guild_name = guild_id
            else:
                guild_name = guild.name

            level = util.get_level(xp)
            total_xp += xp
            rows.append(f"`#{i}` **{guild_name}** — Level **{level}**")

        content = discord.Embed()
        content.set_author(
            name=f"Top servers by XP for {util.displayname(ctx.author, escape=False)}",
            icon_url=ctx.author.avatar_url,
        )
        content.set_footer(text=f"Combined global level {util.get_level(total_xp)}")
        content.colour = ctx.author.color
        await util.send_as_pages(ctx, content, rows)

    @commands.group(case_insensitive=True, aliases=["lb"])
    async def leaderboard(self, ctx):
        """Show various leaderboards."""
        await util.command_group_help(ctx)

    @leaderboard.command(name="fishy")
    async def leaderboard_fishy(self, ctx, scope=""):
        """Fishy leaderboard."""
        global_data = scope.lower() == "global"
        data = await self.bot.db.execute(
            "SELECT user_id, fishy_count FROM fishy ORDER BY fishy_count DESC"
        )

        rows = []
        medal_emoji = [":first_place:", ":second_place:", ":third_place:"]
        i = 1
        for user_id, fishy_count in data:
            if global_data:
                user = self.bot.get_user(user_id)
            else:
                user = ctx.guild.get_member(user_id)

            if user is None or fishy_count == 0:
                continue

            if i <= len(medal_emoji):
                ranking = medal_emoji[i - 1]
            else:
                ranking = f"`#{i:2}`"

            rows.append(f"{ranking} **{util.displayname(user)}** — **{fishy_count}** fishy")
            i += 1

        if not rows:
            raise exceptions.Info("Nobody has any fish yet!")

        content = discord.Embed(
            title=f":fish: {'Global' if global_data else ctx.guild.name} fishy leaderboard",
            color=int("55acee", 16),
        )
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="levels", aliases=["xp", "level"])
    async def leaderboard_levels(self, ctx, scope="", timeframe=""):
        """Activity XP leaderboard."""
        _global_ = scope == "global"
        if timeframe == "":
            timeframe = scope

        time, table = get_activity_table(timeframe)
        if _global_:
            data = await self.bot.db.execute(
                f"""
                SELECT user_id, SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23) as xp,
                    SUM(message_count) FROM {table}
                WHERE NOT is_bot
                GROUP BY user_id ORDER BY xp DESC
                """
            )
        else:
            data = await self.bot.db.execute(
                f"""
                SELECT user_id, SUM(h0+h1+h2+h3+h4+h5+h6+h7+h8+h9+h10+h11+h12+h13+h14+h15+h16+h17+h18+h19+h20+h21+h22+h23) as xp,
                    message_count FROM {table}
                WHERE guild_id = %s AND NOT is_bot
                GROUP BY user_id ORDER BY xp DESC
                """,
                ctx.guild.id,
            )

        rows = []
        for i, (user_id, xp, message_count) in enumerate(data, start=1):
            if _global_:
                user = self.bot.get_user(user_id)
            else:
                user = ctx.guild.get_member(user_id)

            if user is None:
                continue

            if i <= len(self.medal_emoji):
                ranking = self.medal_emoji[i - 1]
            else:
                ranking = f"`#{i:2}`"

            rows.append(
                f"{ranking} **{util.displayname(user)}** — "
                + (f"LVL **{util.get_level(xp)}**, " if time == "" else "")
                + f"**{xp}** XP, **{message_count}** message{'' if message_count == 1 else 's'}"
            )

        content = discord.Embed(
            color=int("5c913b", 16),
            title=f":bar_chart: {'Global' if _global_ else ctx.guild.name} {time}levels leaderboard",
        )

        if not rows:
            rows = ["No data."]

        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="wpm", aliases=["typing"])
    async def leaderboard_wpm(self, ctx, scope=""):
        """Best typing speed high scores leaderboard."""
        _global_ = scope == "global"

        data = await self.bot.db.execute(
            """
            SELECT user_id, MAX(wpm) as wpm, test_date, word_count FROM typing_stats
            GROUP BY user_id ORDER BY wpm DESC
            """
        )

        rows = []
        i = 1
        for userid, wpm, test_date, word_count in data:
            if _global_:
                user = self.bot.get_user(userid)
            else:
                user = ctx.guild.get_member(userid)

            if user is None:
                continue

            if i <= len(self.medal_emoji):
                ranking = self.medal_emoji[i - 1]
            else:
                ranking = f"`#{i:2}`"

            rows.append(
                f"{ranking} **{util.displayname(user)}** — **{int(wpm)}** WPM ({arrow.get(test_date).to('utc').humanize()})"
            )
            i += 1

        if not rows:
            rows = ["No data."]

        content = discord.Embed(
            title=f":keyboard: {ctx.guild.name} WPM leaderboard", color=int("99aab5", 16)
        )
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="crowns")
    async def leaderboard_crowns(self, ctx):
        """Last.fm artist crowns leaderboard."""
        data = await self.bot.db.execute(
            """
            SELECT user_id, COUNT(1) as amount FROM artist_crown
            WHERE guild_id = %s GROUP BY user_id ORDER BY amount DESC
            """,
            ctx.guild.id,
        )
        rows = []
        for i, (user_id, amount) in enumerate(data, start=1):
            user = ctx.guild.get_member(user_id)
            if user is None:
                continue

            if i <= len(self.medal_emoji):
                ranking = self.medal_emoji[i - 1]
            else:
                ranking = f"`#{i:2}`"

            rows.append(f"{ranking} **{util.displayname(user)}** — **{amount}** crowns")

        content = discord.Embed(
            color=int("ffcc4d", 16), title=f":crown: {ctx.guild.name} artist crowns leaderboard"
        )
        if not rows:
            rows = ["No data."]

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

        if user.id == self.bot.owner_id:
            badges.append(make_badge(badge_classes["dev"]))

        if user.bot:
            badges.append(make_badge(badge_classes["bot"]))

        if await queries.is_donator(ctx, user):
            badges.append(make_badge(badge_classes["patreon"]))

        user_settings = await self.bot.db.execute(
            "SELECT lastfm_username, sunsign, location_string FROM user_settings WHERE user_id = %s",
            user.id,
            one_row=True,
        )
        if user_settings:
            if user_settings[0] is not None:
                badges.append(make_badge(badge_classes["lastfm"]))
            if user_settings[1] is not None:
                badges.append(make_badge(badge_classes["sunsign"]))
            if user_settings[2] is not None:
                badges.append(make_badge(badge_classes["location"]))

        server_activity = await self.bot.db.execute(
            """
            SELECT h0,h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,20,h21,h22,h23 as xp
                FROM user_activity
            WHERE user_id = %s AND guild_id = %s
            """,
            user.id,
            ctx.guild.id,
            one_row=True,
        )
        server_xp = sum(server_activity) if server_activity else 0

        global_activity = await self.bot.db.execute(
            """
            SELECT h0,h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,20,h21,h22,h23 as xp
                FROM user_activity
            WHERE user_id = %s
            GROUP BY guild_id
            """,
            user.id,
        )
        if global_activity:
            new_global_activity = []
            for i in range(24):
                new_global_activity.append(sum(r[i] for r in global_activity))
            global_xp = sum(new_global_activity)
        else:
            new_global_activity = [0] * 24
            global_xp = 0

        if user.bot:
            description = "I am a bot<br>BEEP BOOP"
        else:
            description = "You should change this by using<br>>editprofile description"

        profile_data = await self.bot.db.execute(
            """
            SELECT description, background_url, background_color, show_graph
            FROM user_profile WHERE user_id = %s
            """,
            user.id,
            one_row=True,
        )

        fishy = await self.bot.db.execute(
            """
            SELECT fishy_count FROM fishy WHERE user_id = %s
            """,
            user.id,
            one_value=True,
        )

        if profile_data:
            description, background_url, background_color, show_graph = profile_data
            if description is not None:
                description = bleach.clean(
                    description.replace("\n", "<br>"),
                    tags=bleach.sanitizer.ALLOWED_TAGS + ["br"],
                )
            background_url = background_url or ""
            background_color = (
                ("#" + background_color) if background_color is not None else user.color
            )
        else:
            background_color = user.color
            background_url = ""
            show_graph = True

        command_uses = await self.bot.db.execute(
            """
            SELECT SUM(uses) FROM command_usage WHERE user_id = %s
            GROUP BY user_id
            """,
            user.id,
            one_value=True,
        )

        replacements = {
            "BACKGROUND_IMAGE": background_url,
            "WRAPPER_CLASS": "custom-bg" if background_url != "" else "",
            "SIDEBAR_CLASS": "blur" if background_url != "" else "",
            "OVERLAY_CLASS": "overlay" if background_url != "" else "",
            "USER_COLOR": background_color,
            "AVATAR_URL": user.avatar_url_as(size=128, format="png"),
            "USERNAME": user.name,
            "DISCRIMINATOR": f"#{user.discriminator}",
            "DESCRIPTION": description,
            "FISHY_AMOUNT": fishy or 0,
            "SERVER_LEVEL": util.get_level(server_xp),
            "GLOBAL_LEVEL": util.get_level(global_xp),
            "ACTIVITY_DATA": str(new_global_activity),
            "CHART_MAX": max(new_global_activity),
            "COMMANDS_USED": command_uses or 0,
            "BADGES": "\n".join(badges),
            "USERNAME_SIZE": get_font_size(user.name),
            "SHOW_GRAPH": "true" if show_graph else "false",
            "DESCRIPTION_HEIGHT": "250px" if show_graph else "350px",
        }

        payload = {
            "html": util.format_html(self.profile_html, replacements),
            "width": 600,
            "height": 400,
            "imageFormat": "png",
        }
        buffer = await util.render_html(payload)
        await ctx.send(file=discord.File(fp=buffer, filename=f"profile_{user.name}.png"))

    @commands.group()
    async def editprofile(self, ctx):
        """Edit your profile."""
        await util.command_group_help(ctx)

    @editprofile.command(name="description", rest_is_raw=True)
    async def editprofile_description(self, ctx, *, text):
        """Change the description on your profile."""
        if text.strip() == "":
            return await util.send_command_help(ctx)

        if len(text) > 500:
            raise exceptions.Warning(
                f"Description cannot be more than 500 characters ({len(text)})"
            )

        await self.bot.db.execute(
            """
            INSERT INTO user_profile (user_id, description)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                description = VALUES(description)
            """,
            ctx.author.id,
            text,
        )
        await util.send_success(ctx, "Profile description updated!")

    @util.patrons_only()
    @editprofile.command(name="background")
    async def editprofile_background(self, ctx, url):
        """Set a custom background image. Only works with direct link to image."""
        await self.bot.db.execute(
            """
            INSERT INTO user_profile (user_id, background_url)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                background_url = VALUES(background_url)
            """,
            ctx.author.id,
            url,
        )
        await util.send_success(ctx, "Profile background image updated!")

    @util.patrons_only()
    @editprofile.command(name="graph")
    async def editprofile_graph(self, ctx, value: bool):
        """Toggle whether to show activity graph on your profile or not."""
        await self.bot.db.execute(
            """
            INSERT INTO user_profile (user_id, show_graph)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                show_graph = VALUES(show_graph)
            """,
            ctx.author.id,
            value,
        )
        if value:
            await util.send_success(ctx, "Now showing activity graph on your profile.")
        else:
            await util.send_success(ctx, "Activity graph on your profile is now hidden.")

    @editprofile.command(name="color", aliases=["colour"])
    async def editprofile_color(self, ctx, color):
        """
        Set a background color to be used instead of your role color.
        Set as \"default\" to use role color again.
        """
        if color.lower() == "default":
            color_value = None
        else:
            color_hex = await util.get_color(ctx, color)
            if color_hex is None:
                raise exceptions.Warning(f"Invalid color {color}")
            else:
                color_value = str(color_hex).strip("#")

        await self.bot.db.execute(
            """
            INSERT INTO user_profile (user_id, background_color)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                background_color = VALUES(background_color)
            """,
            ctx.author.id,
            color_value,
        )
        await util.send_success(
            ctx, f"Profile background color set to `{color_value or 'default'}`!"
        )


def setup(bot):
    bot.add_cog(User(bot))


def get_activity_table(timeframe):
    if timeframe in ["day", "daily"]:
        return "daily ", "user_activity_day"
    if timeframe in ["week", "weekly"]:
        return "weekly ", "user_activity_week"
    if timeframe in ["month", "monthly"]:
        return "monthly ", "user_activity_month"
    if timeframe in ["year", "yearly"]:
        return "yearly ", "user_activity_year"
    else:
        return "", "user_activity"
